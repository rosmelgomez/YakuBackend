import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import (
    asignaciones_iot,
    configuracion_control,
    configuracion_tanque,
    riego,
)

logger = logging.getLogger(__name__)


MIN_RELAY_MINUTES = 1
MAX_RELAY_MINUTES = 30
DEFAULT_RELAY_MINUTES = 10
TRANSIENT_STOP_REASONS = {"sin_agua", "sensor_error", "tanque_llenandose", "apagado_manual"}


def clamp_duration_seconds(value: int | None) -> int:
    default_seconds = DEFAULT_RELAY_MINUTES * 60
    if value is None:
        return default_seconds
    return max(MIN_RELAY_MINUTES * 60, min(int(value), MAX_RELAY_MINUTES * 60))


def get_max_relay_seconds(db: Session, user_id: int, crop_id: int | None) -> int:
    config = db.query(configuracion_control).filter(
        configuracion_control.id_usuario == user_id,
        configuracion_control.id_cultivo == crop_id,
    ).first()
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

    from src.tasks.mqtt_subscriber import publish_mqtt_message

    topic = device.topic_sub or "yaku/riego/comando"
    # Un ON retenido podria volver a encender el rele despues de reiniciar el ESP32.
    publish_mqtt_message(topic, payload, qos=1, retain=False)


def find_pump_assignment(db: Session, user_id: int, crop_id: int) -> asignaciones_iot | None:
    return db.query(asignaciones_iot).join(
        configuracion_tanque,
        configuracion_tanque.id_asignacion == asignaciones_iot.id,
    ).filter(
        asignaciones_iot.id_usuario == user_id,
        asignaciones_iot.id_cultivo == crop_id,
        asignaciones_iot.activo == True,
    ).first()


def is_paused_session(session: riego | None) -> bool:
    return bool(session and session.motivo_cierre and session.motivo_cierre.startswith("pausado_"))


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
    from ..db.models import asignaciones_iot
    asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == pump_assignment_id).first()
    if asig:
        # 1. Buscar asignacion de sensor (NIVEL_AGUA, tipo_metrica 5) en el mismo cultivo
        sensor_asig = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_cultivo == asig.id_cultivo,
            asignaciones_iot.id_tipo_metrica == 5
        ).first()
        if sensor_asig:
            return sensor_asig.id
        # 2. Fallback a cualquier asignacion del mismo dispositivo que no sea la bomba (tipo_metrica 5)
        # o simplemente la primera asignacion de ese dispositivo
        sensor_asig = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_dispositivo == asig.id_dispositivo
        ).order_by(asignaciones_iot.id_tipo_metrica.desc().nullslast()).first()
        if sensor_asig:
            return sensor_asig.id
    return pump_assignment_id


def start_new_execution(db: Session, session: riego, now: datetime) -> None:
    from ..db.models import telemetria_tanque, ejecucion_riego
    sensor_id = _find_sensor_assignment_id(db, session.id_asignacion)
    last_tel = db.query(telemetria_tanque).filter(
        telemetria_tanque.id_asignacion == sensor_id
    ).order_by(telemetria_tanque.id.desc()).first()
    
    distancia_inicial = float(last_tel.distancia_cm) if (last_tel and last_tel.distancia_cm is not None) else None
    
    execution = ejecucion_riego(
        id_riego=session.id,
        fecha_inicio=now,
        distancia_inicial_cm=distancia_inicial,
        duracion_segundos=0,
        cantidad_agua_litros=0.0
    )
    db.add(execution)
    db.flush()
    _publish_pump_status(db, session, "ON")


def _close_active_execution(
    db: Session,
    session: riego,
    reason: str,
    now: datetime,
    override_litros: float | None = None,
    override_duration_seconds: int | None = None,
) -> float:
    from ..db.models import telemetria_tanque, ejecucion_riego, fuentes_agua, asignaciones_iot
    execution = db.query(ejecucion_riego).filter(
        ejecucion_riego.id_riego == session.id,
        ejecucion_riego.fecha_fin.is_(None)
    ).order_by(ejecucion_riego.id.desc()).first()
    
    if not execution:
        return 0.0
        
    execution.fecha_fin = now
    execution.motivo_cierre = reason
    if override_duration_seconds is not None:
        execution.duracion_segundos = max(int(override_duration_seconds), 0)
    else:
        execution.duracion_segundos = max(int((now - execution.fecha_inicio).total_seconds()), 0)
    
    sensor_id = _find_sensor_assignment_id(db, session.id_asignacion)
    last_tel = db.query(telemetria_tanque).filter(
        telemetria_tanque.id_asignacion == sensor_id
    ).order_by(telemetria_tanque.id.desc()).first()
    
    distancia_final = float(last_tel.distancia_cm) if (last_tel and last_tel.distancia_cm is not None) else None
    execution.distancia_final_cm = distancia_final
    
    litros = 0.0
    if override_litros is not None:
        litros = override_litros
    else:
        if execution.distancia_inicial_cm is not None and distancia_final is not None:
            delta_dist = float(distancia_final) - float(execution.distancia_inicial_cm)
            if delta_dist > 0:
                asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == session.id_asignacion).first()
                fuente = None
                if asig and asig.id_fuente_agua is not None:
                    fuente = db.query(fuentes_agua).filter(fuentes_agua.id == asig.id_fuente_agua).first()
                if fuente and fuente.capacidad_litros and fuente.altura_tanque_cm:
                    litros_por_cm = float(fuente.capacidad_litros) / float(fuente.altura_tanque_cm)
                    litros = delta_dist * litros_por_cm
                    
    execution.cantidad_agua_litros = litros
    db.add(execution)
    db.flush()
    return litros


def _publish_pump_status(db: Session, session: riego, state: str) -> None:
    try:
        from ..db.models import asignaciones_iot
        asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == session.id_asignacion).first()
        if asig and asig.dispositivo:
            client_id = asig.dispositivo.client_id_mqtt or "ESP32_Yaku_Unknown"
            topic = f"yaku/dispositivo/{client_id}/bomba/estado"
            payload = json.dumps({
                "id_riego": session.id,
                "estado_bomba": state,
                "segundos_acumulados": int(session.segundos_acumulados or 0),
                "cantidad_agua_litros": float(session.cantidad_agua_litros or 0.0),
                "fecha": datetime.now(timezone.utc).isoformat()
            })
            from src.tasks.mqtt_subscriber import publish_mqtt_message
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
    
    from ..db.models import ejecucion_riego
    db.flush()
    total_seconds = db.query(func.sum(ejecucion_riego.duracion_segundos)).filter(ejecucion_riego.id_riego == session.id).scalar() or 0
    total_litros = db.query(func.sum(ejecucion_riego.cantidad_agua_litros)).filter(ejecucion_riego.id_riego == session.id).scalar() or 0.0
    
    planned = planned_seconds(session)
    session.segundos_acumulados = min(total_seconds, planned) if planned > 0 else total_seconds
    session.cantidad_agua_litros = total_litros
    session.motivo_cierre = f"pausado_{reason}_{session.segundos_acumulados}"
    session.estado = False
    session.fecha = current
    db.add(session)
    db.flush()
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
    
    from ..db.models import ejecucion_riego
    db.flush()
    total_seconds = db.query(func.sum(ejecucion_riego.duracion_segundos)).filter(ejecucion_riego.id_riego == session.id).scalar() or 0
    total_litros = db.query(func.sum(ejecucion_riego.cantidad_agua_litros)).filter(ejecucion_riego.id_riego == session.id).scalar() or 0.0
    
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
    db.add(session)
    db.flush()
    _publish_pump_status(db, session, "OFF")


def resume_irrigation(
    db: Session,
    assignment: asignaciones_iot,
    session: riego | None = None,
    publish: bool = True,
    now: datetime | None = None,
) -> riego | None:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    
    from ..db.models import configuracion_tanque
    tank_config = db.query(configuracion_tanque).filter(
        configuracion_tanque.id_asignacion == assignment.id
    ).first()
    if tank_config and bool(tank_config.valvula_abierta):
        raise ValueError("No se puede reanudar el riego: el tanque se está rellenando.")

    if session is None:
        session = db.query(riego).filter(
            riego.id_asignacion == assignment.id,
            riego.estado == False,
            riego.motivo_cierre.like("pausado_%"),
        ).order_by(riego.id.desc()).first()
    if session is None:
        return None

    remaining = remaining_seconds(session, current)
    if remaining <= 0:
        complete_irrigation_session(db, session, "tiempo_maximo", current)
        db.commit()
        return session

    session.motivo_cierre = None
    session.fecha = current
    db.add(session)
    db.flush()
    
    start_new_execution(db, session, current)

    tank_config = db.query(configuracion_tanque).filter(
        configuracion_tanque.id_asignacion == assignment.id
    ).first()
    if tank_config:
        tank_config.bomba_encendida = True
        tank_config.actualizado_en = current
        db.add(tank_config)

    if publish:
        _publish_relay_command(assignment, build_relay_command("ON", remaining))
    db.commit()
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
    
    from ..db.models import configuracion_tanque
    tank_config = db.query(configuracion_tanque).filter(
        configuracion_tanque.id_asignacion == assignment.id
    ).first()
    if tank_config and bool(tank_config.valvula_abierta):
        raise ValueError("No se puede iniciar el riego: el tanque se está rellenando.")

    active = db.query(riego).filter(
        riego.id_asignacion == assignment.id,
        riego.estado == False,
    ).order_by(riego.id.desc()).first()
    if active:
        if is_paused_session(active):
            resume_irrigation(db, assignment, active, now=current)
            return active

        remaining = remaining_seconds(active, current)
        if remaining <= 0:
            complete_irrigation_session(db, active, "tiempo_maximo", current)
            db.commit()
        else:
            tank_config = db.query(configuracion_tanque).filter(
                configuracion_tanque.id_asignacion == assignment.id
            ).first()
            if tank_config is None or not bool(tank_config.bomba_encendida):
                # Start new execution block if pump was conmuted ON
                active.fecha = current
                db.add(active)
                if tank_config:
                    tank_config.bomba_encendida = True
                    tank_config.actualizado_en = current
                    db.add(tank_config)
                db.flush()
                start_new_execution(db, active, current)
                _publish_relay_command(assignment, build_relay_command("ON", remaining))
                db.commit()
                db.refresh(active)
            return active

    maximum = get_max_relay_seconds(db, assignment.id_usuario, assignment.id_cultivo)
    duration = maximum if requested_seconds is None else min(
        clamp_duration_seconds(requested_seconds), maximum
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
    db.add(session)
    db.flush()
    
    start_new_execution(db, session, current)

    tank_config = db.query(configuracion_tanque).filter(
        configuracion_tanque.id_asignacion == assignment.id
    ).first()
    if tank_config:
        tank_config.bomba_encendida = True
        tank_config.actualizado_en = current
        db.add(tank_config)

    _publish_relay_command(assignment, build_relay_command("ON", duration))
    db.commit()
    db.refresh(session)
    return session


def stop_irrigation(
    db: Session,
    assignment: asignaciones_iot,
    reason: str,
    publish: bool = True,
    now: datetime | None = None,
) -> riego | None:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    session = db.query(riego).filter(
        riego.id_asignacion == assignment.id,
        riego.estado == False,
    ).order_by(riego.id.desc()).first()

    if session:
        if reason in TRANSIENT_STOP_REASONS:
            pause_irrigation_session(db, session, reason, current)
        else:
            complete_irrigation_session(db, session, reason, current)

    tank_config = db.query(configuracion_tanque).filter(
        configuracion_tanque.id_asignacion == assignment.id
    ).first()
    if tank_config:
        tank_config.bomba_encendida = False
        tank_config.actualizado_en = current
        db.add(tank_config)

    if publish:
        _publish_relay_command(assignment, build_relay_command("OFF"))
    db.commit()
    return session
