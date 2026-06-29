import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models import (
    asignaciones_iot,
    configuracion_control,
    configuracion_tanque,
    dispositivos,
    riego,
)


MIN_RELAY_MINUTES = 1
MAX_RELAY_MINUTES = 30
DEFAULT_RELAY_MINUTES = 10
TRANSIENT_STOP_REASONS = {"sin_agua", "sensor_error"}


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


def pause_irrigation_session(
    db: Session,
    session: riego,
    reason: str,
    now: datetime | None = None,
    litros: float | None = None,
) -> None:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    planned = planned_seconds(session)
    elapsed = executed_seconds(session, current)
    session.segundos_acumulados = min(elapsed, planned) if planned > 0 else elapsed
    session.motivo_cierre = f"pausado_{reason}_{session.segundos_acumulados}"
    session.estado = False
    session.fecha = current
    if litros is not None:
        session.cantidad_agua_litros = float(session.cantidad_agua_litros or 0.0) + max(litros, 0.0)
    db.add(session)


def complete_irrigation_session(
    db: Session,
    session: riego,
    reason: str,
    now: datetime | None = None,
    litros: float | None = None,
) -> None:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    planned = planned_seconds(session)
    elapsed = executed_seconds(session, current)
    final_elapsed = min(elapsed, planned) if planned > 0 and reason == "tiempo_maximo" else elapsed
    session.segundos_acumulados = max(final_elapsed, 1)
    session.duracion_segundos = max(session.segundos_acumulados, 1)
    session.estado = True
    session.fecha_fin = current
    session.fecha = current
    session.motivo_cierre = reason
    if litros is not None:
        session.cantidad_agua_litros = float(session.cantidad_agua_litros or 0.0) + max(litros, 0.0)
    db.add(session)


def resume_irrigation(
    db: Session,
    assignment: asignaciones_iot,
    session: riego | None = None,
    publish: bool = True,
) -> riego | None:
    current = datetime.now(timezone.utc).replace(tzinfo=None)
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
) -> riego:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    active = db.query(riego).filter(
        riego.id_asignacion == assignment.id,
        riego.estado == False,
    ).order_by(riego.id.desc()).first()
    if active:
        if is_paused_session(active):
            resume_irrigation(db, assignment, active)
            return active

        remaining = remaining_seconds(active, now)
        if remaining <= 0:
            complete_irrigation_session(db, active, "tiempo_maximo", now)
            db.commit()
        else:
            tank_config = db.query(configuracion_tanque).filter(
                configuracion_tanque.id_asignacion == assignment.id
            ).first()
            if tank_config is None or not bool(tank_config.bomba_encendida):
                active.segundos_acumulados = max(
                    int(active.segundos_acumulados or 0),
                    max(int(active.duracion_segundos or 0) - remaining, 0),
                )
                active.fecha = now
                db.add(active)
                if tank_config:
                    tank_config.bomba_encendida = True
                    tank_config.actualizado_en = now
                    db.add(tank_config)
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
        fecha_inicio=now,
        fecha_fin=None,
        fecha=now,
    )
    db.add(session)

    tank_config = db.query(configuracion_tanque).filter(
        configuracion_tanque.id_asignacion == assignment.id
    ).first()
    if tank_config:
        tank_config.bomba_encendida = True
        tank_config.actualizado_en = now
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
) -> riego | None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session = db.query(riego).filter(
        riego.id_asignacion == assignment.id,
        riego.estado == False,
    ).order_by(riego.id.desc()).first()

    if session:
        if reason in TRANSIENT_STOP_REASONS:
            pause_irrigation_session(db, session, reason, now)
        else:
            complete_irrigation_session(db, session, reason, now)

    tank_config = db.query(configuracion_tanque).filter(
        configuracion_tanque.id_asignacion == assignment.id
    ).first()
    if tank_config:
        tank_config.bomba_encendida = False
        tank_config.actualizado_en = now
        db.add(tank_config)

    if publish:
        _publish_relay_command(assignment, build_relay_command("OFF"))
    db.commit()
    return session
