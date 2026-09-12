import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.main.model.models import (
    asignaciones_iot,
    riego,
)
from src.main.repositories import irrigationRep as data_repository
from src.main.repositories import sessionRep as session_repository

logger = logging.getLogger(__name__)


MIN_RELAY_MINUTES = 1
MAX_RELAY_MINUTES = 30
DEFAULT_RELAY_MINUTES = 10
TRANSIENT_STOP_REASONS = {
    "sin_agua",
    "sin_flujo",
    "sensor_error",
    "tanque_llenandose",
    "apagado_manual",
}


def clamp_duration_seconds(value: int | None) -> int:
    default_seconds = DEFAULT_RELAY_MINUTES * 60
    if value is None:
        return default_seconds
    return max(MIN_RELAY_MINUTES * 60, min(int(value), MAX_RELAY_MINUTES * 60))


def get_max_relay_seconds(db: Session, user_id: int, crop_id: int | None) -> int:
    config = data_repository.queryGetMaxRelaySecondsConfig(db, user_id, crop_id)
    return clamp_duration_seconds(config.duracion_riego_max_seg if config else None)


def build_relay_command(action: str, duration_seconds: int | None = None) -> str:
    payload: dict[str, object] = {"accion": action.upper()}
    if action.upper() == "ON":
        payload["duracion_seg"] = clamp_duration_seconds(duration_seconds)
    return json.dumps(payload, separators=(",", ":"))


def build_valve_command(open_valve: bool) -> str:
    return json.dumps(
        {"accion": "VALVULA_ON" if open_valve else "VALVULA_OFF"},
        separators=(",", ":"),
    )


def _publish_relay_command(assignment: asignaciones_iot, payload: str) -> None:
    device = assignment.dispositivo
    if device is None:
        device = None
    if device is None:
        raise ValueError("La asignacion no tiene un dispositivo asociado.")

    from src.main.tasks.mqttSubscriberTask import publish_mqtt_message

    topic = device.topic_sub or "yaku/riego/comando"
    # Un ON retenido podria volver a encender el rele despues de reiniciar el ESP32.
    publish_mqtt_message(topic, payload, qos=1, retain=False)


def find_pump_assignment(
    db: Session, user_id: int, crop_id: int
) -> asignaciones_iot | None:
    return data_repository.queryFindPumpAssignmentResultado(db, user_id, crop_id)


def is_paused_session(session: riego | None) -> bool:
    return bool(
        session
        and session.motivo_cierre
        and data_repository.queryIsPausedSessionStartswith(session)
    )


def _accumulated_seconds(session: riego) -> int:
    return max(int(session.segundos_acumulados or 0), 0)


def _segment_elapsed_seconds(session: riego, now: datetime) -> int:
    if is_paused_session(session) or session.fecha is None:
        return 0
    return max(int((now - session.fecha).total_seconds()), 0)


def planned_seconds(session: riego) -> int:
    return max(int(session.duracion_segundos or 0), 0)


def executed_seconds(session: riego, now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return _accumulated_seconds(session) + _segment_elapsed_seconds(session, current)


def remaining_seconds(session: riego, now: datetime | None = None) -> int:
    planned = planned_seconds(session)
    if planned <= 0:
        return 0
    return max(planned - executed_seconds(session, now), 0)


# Helper functions for tracking pump executions
def _find_sensor_assignment_id(db: Session, pump_assignment_id: int) -> int:
    asig = data_repository.queryFindSensorAssignmentIdAsig(db, pump_assignment_id)
    if asig:
        # 1. Buscar asignacion de sensor (NIVEL_AGUA, tipo_metrica 5) en el mismo cultivo
        sensor_asig = data_repository.queryFindSensorAssignmentIdSensorAsig(db, asig)
        if sensor_asig:
            return sensor_asig.id
        # 2. Fallback a cualquier asignacion del mismo dispositivo que no sea la bomba (tipo_metrica 5)
        # o simplemente la primera asignacion de ese dispositivo
        sensor_asig = data_repository.queryFindSensorAssignmentIdSensorAsig2(db, asig)
        if sensor_asig:
            return sensor_asig.id
    return pump_assignment_id


def start_new_execution(db: Session, session: riego, now: datetime) -> None:
    from src.main.model.models import ejecucion_riego
    from src.main.service.waterMeasurementServ import measurement_method

    assignment = data_repository.queryFindSensorAssignmentIdAsig(db, session.id_asignacion)
    method = measurement_method(assignment)

    sensor_id = _find_sensor_assignment_id(db, session.id_asignacion)
    last_tel = data_repository.queryStartNewExecutionLastTel(db, sensor_id)

    distancia_inicial = (
        float(last_tel.distancia_cm)
        if (last_tel and last_tel.distancia_cm is not None)
        else None
    )

    execution = ejecucion_riego(
        id_riego=session.id,
        fecha_inicio=now,
        metodo_medicion=method,
        distancia_inicial_cm=distancia_inicial,
        duracion_segundos=0,
        cantidad_agua_litros=0.0,
    )
    session_repository.add(db, execution)
    session_repository.flush(db)
    _publish_pump_status(db, session, "ON")


def _close_active_execution(
    db: Session,
    session: riego,
    reason: str,
    now: datetime,
    override_litros: float | None = None,
    override_duration_seconds: int | None = None,
) -> float:
    execution = data_repository.queryCloseActiveExecutionExecution(db, session)

    if not execution:
        return 0.0

    execution.fecha_fin = now
    execution.motivo_cierre = reason
    if override_duration_seconds is not None:
        execution.duracion_segundos = max(int(override_duration_seconds), 0)
    else:
        execution.duracion_segundos = max(
            int((now - execution.fecha_inicio).total_seconds()), 0
        )

    sensor_id = _find_sensor_assignment_id(db, session.id_asignacion)
    last_tel = data_repository.queryCloseActiveExecutionLastTel(db, sensor_id)

    distancia_final = (
        float(last_tel.distancia_cm)
        if (last_tel and last_tel.distancia_cm is not None)
        else None
    )
    execution.distancia_final_cm = distancia_final

    # Con distancia -1 la conexion directa reporta el volumen del caudalimetro.
    # Conservar el ultimo reporte si el servidor cierra antes del OFF del equipo.
    litros = (
        float(execution.cantidad_agua_litros or 0.0)
        if getattr(execution, "metodo_medicion", None) == "flujometro" or execution.distancia_inicial_cm == -1
        else 0.0
    )
    if override_litros is not None:
        litros = override_litros
    elif getattr(execution, "metodo_medicion", None) != "flujometro":
        if execution.distancia_inicial_cm is not None and distancia_final is not None:
            delta_dist = float(distancia_final) - float(execution.distancia_inicial_cm)
            if delta_dist > 0:
                asig = data_repository.queryCloseActiveExecutionAsig(db, session)
                fuente = None
                if asig and asig.id_fuente_agua is not None:
                    fuente = data_repository.queryCloseActiveExecutionFuente(db, asig)
                if fuente is None and asig and asig.cultivo is not None:
                    fuente = asig.cultivo.fuente_agua
                if fuente and fuente.capacidad_litros and fuente.altura_tanque_cm:
                    litros_por_cm = float(fuente.capacidad_litros) / float(
                        fuente.altura_tanque_cm
                    )
                    litros = delta_dist * litros_por_cm

    execution.cantidad_agua_litros = litros
    session_repository.add(db, execution)
    session_repository.flush(db)
    return litros


def _publish_pump_status(db: Session, session: riego, state: str) -> None:
    try:
        asig = data_repository.queryPublishPumpStatusAsig(db, session)
        if asig and asig.dispositivo:
            client_id = asig.dispositivo.client_id_mqtt or "ESP32_Yaku_Unknown"
            topic = f"yaku/dispositivo/{client_id}/bomba/estado"
            payload = json.dumps(
                {
                    "id_riego": session.id,
                    "estado_bomba": state,
                    "segundos_acumulados": int(session.segundos_acumulados or 0),
                    "cantidad_agua_litros": float(session.cantidad_agua_litros or 0.0),
                    "fecha": datetime.now(timezone.utc).isoformat(),
                }
            )
            from src.main.tasks.mqttSubscriberTask import publish_mqtt_message

            publish_mqtt_message(topic, payload, qos=1, retain=True)
            logger.info(f"[MQTT STATUS] Estado publicado en {topic}: {payload}")
    except Exception as exc:
        logger.warning(f"No se pudo publicar estado de la bomba via MQTT: {exc}")


def pause_irrigation_session(
    db: Session,
    session: riego,
    reason: str,
    now: datetime | None = None,
    litros: float | None = None,
    executed_seconds_override: int | None = None,
) -> None:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    _close_active_execution(
        db,
        session,
        reason,
        current,
        override_litros=litros,
        override_duration_seconds=executed_seconds_override,
    )

    session_repository.flush(db)
    total_seconds = (
        data_repository.queryPauseIrrigationSessionEjecucionRiego(db, session) or 0
    )
    total_litros = (
        data_repository.queryPauseIrrigationSessionEjecucionRiego2(db, session) or 0.0
    )

    planned = planned_seconds(session)
    session.segundos_acumulados = (
        min(total_seconds, planned) if planned > 0 else total_seconds
    )
    session.cantidad_agua_litros = total_litros
    session.motivo_cierre = f"pausado_{reason}_{session.segundos_acumulados}"
    session.estado = False
    session.fecha = current
    session_repository.add(db, session)
    session_repository.flush(db)
    _publish_pump_status(db, session, "OFF")


def complete_irrigation_session(
    db: Session,
    session: riego,
    reason: str,
    now: datetime | None = None,
    litros: float | None = None,
) -> None:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    _close_active_execution(db, session, reason, current, override_litros=litros)

    session_repository.flush(db)
    total_seconds = (
        data_repository.queryCompleteIrrigationSessionEjecucionRiego(db, session) or 0
    )
    total_litros = (
        data_repository.queryCompleteIrrigationSessionEjecucionRiego2(db, session)
        or 0.0
    )

    planned = planned_seconds(session)
    session.segundos_acumulados = max(total_seconds, 1)
    if reason == "tiempo_maximo" and planned > 0:
        session.segundos_acumulados = min(total_seconds, planned)

    session.duracion_segundos = max(session.segundos_acumulados, 1)
    session.cantidad_agua_litros = total_litros
    session.estado = True
    session.fecha_fin = current
    session.fecha = current
    session.motivo_cierre = reason
    session_repository.add(db, session)
    session_repository.flush(db)
    _publish_pump_status(db, session, "OFF")


def resume_irrigation(
    db: Session,
    assignment: asignaciones_iot,
    session: riego | None = None,
    publish: bool = True,
    now: datetime | None = None,
) -> riego | None:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)

    tank_config = data_repository.queryResumeIrrigationTankConfig(db, assignment)
    if tank_config and bool(tank_config.valvula_abierta):
        raise ValueError("No se puede reanudar el riego: el tanque se está rellenando.")

    if session is None:
        session = data_repository.queryResumeIrrigationSession(db, assignment)
    if session is None:
        return None

    remaining = remaining_seconds(session, current)
    if remaining <= 0:
        complete_irrigation_session(db, session, "tiempo_maximo", current)
        session_repository.commit(db)
        return session

    session.motivo_cierre = None
    session.fecha = current
    session_repository.add(db, session)
    session_repository.flush(db)

    start_new_execution(db, session, current)

    tank_config = data_repository.queryResumeIrrigationTankConfig2(db, assignment)
    if tank_config:
        tank_config.bomba_encendida = True
        tank_config.actualizado_en = current
        session_repository.add(db, tank_config)

    if publish:
        _publish_relay_command(assignment, build_relay_command("ON", remaining))
    session_repository.commit(db)
    return session


def start_irrigation(
    db: Session,
    assignment: asignaciones_iot,
    irrigation_type: str,
    requested_seconds: int | None = None,
    model_id: int | None = None,
    prediction_id: int | None = None,
    now: datetime | None = None,
) -> riego:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)

    tank_config = data_repository.queryStartIrrigationTankConfig(db, assignment)
    if tank_config and bool(tank_config.valvula_abierta):
        raise ValueError("No se puede iniciar el riego: el tanque se está rellenando.")

    active = data_repository.queryStartIrrigationActive(db, assignment)
    if active:
        if is_paused_session(active):
            resume_irrigation(db, assignment, active, now=current)
            return active

        remaining = remaining_seconds(active, current)
        if remaining <= 0:
            complete_irrigation_session(db, active, "tiempo_maximo", current)
            session_repository.commit(db)
        else:
            tank_config = data_repository.queryStartIrrigationTankConfig2(
                db, assignment
            )
            if tank_config is None or not bool(tank_config.bomba_encendida):
                # Start new execution block if pump was conmuted ON
                active.fecha = current
                session_repository.add(db, active)
                if tank_config:
                    tank_config.bomba_encendida = True
                    tank_config.actualizado_en = current
                    session_repository.add(db, tank_config)
                session_repository.flush(db)
                start_new_execution(db, active, current)
                _publish_relay_command(assignment, build_relay_command("ON", remaining))
                session_repository.commit(db)
                session_repository.refresh(db, active)
            return active

    maximum = get_max_relay_seconds(db, assignment.id_usuario, assignment.id_cultivo)
    duration = (
        maximum
        if requested_seconds is None
        else min(clamp_duration_seconds(requested_seconds), maximum)
    )
    session = riego(
        id_asignacion=assignment.id,
        id_usuario=assignment.id_usuario,
        id_modelo=model_id,
        id_prediccion=prediction_id,
        tipo_riego=irrigation_type,
        duracion_segundos=duration,
        segundos_acumulados=0,
        cantidad_agua_litros=0.0,
        estado=False,
        fecha_inicio=current,
        fecha_fin=None,
        fecha=current,
    )
    session_repository.add(db, session)
    session_repository.flush(db)

    start_new_execution(db, session, current)

    tank_config = data_repository.queryStartIrrigationTankConfig3(db, assignment)
    if tank_config:
        tank_config.bomba_encendida = True
        tank_config.actualizado_en = current
        session_repository.add(db, tank_config)

    _publish_relay_command(assignment, build_relay_command("ON", duration))
    session_repository.commit(db)
    session_repository.refresh(db, session)
    return session


def stop_irrigation(
    db: Session,
    assignment: asignaciones_iot,
    reason: str,
    publish: bool = True,
    now: datetime | None = None,
) -> riego | None:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    session = data_repository.queryStopIrrigationSession(db, assignment)

    if session:
        if reason in TRANSIENT_STOP_REASONS:
            pause_irrigation_session(db, session, reason, current)
        else:
            complete_irrigation_session(db, session, reason, current)

    tank_config = data_repository.queryStopIrrigationTankConfig(db, assignment)
    if tank_config:
        tank_config.bomba_encendida = False
        tank_config.actualizado_en = current
        session_repository.add(db, tank_config)

    if publish:
        _publish_relay_command(assignment, build_relay_command("OFF"))
    session_repository.commit(db)
    return session
