import json
from datetime import datetime

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


def start_irrigation(
    db: Session,
    assignment: asignaciones_iot,
    irrigation_type: str,
    requested_seconds: int | None = None,
    model_id: int | None = None,
    prediction_id: int | None = None,
) -> riego:
    active = db.query(riego).filter(
        riego.id_asignacion == assignment.id,
        riego.estado == False,
    ).order_by(riego.id.desc()).first()
    if active:
        return active

    maximum = get_max_relay_seconds(db, assignment.id_usuario, assignment.id_cultivo)
    duration = maximum if requested_seconds is None else min(
        clamp_duration_seconds(requested_seconds), maximum
    )
    now = datetime.now()
    session = riego(
        id_asignacion=assignment.id,
        id_usuario=assignment.id_usuario,
        id_modelo=model_id,
        id_prediccion=prediction_id,
        tipo_riego=irrigation_type,
        duracion_segundos=duration,
        cantidad_agua_litros=0.0,
        estado=False,
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
    now = datetime.now()
    session = db.query(riego).filter(
        riego.id_asignacion == assignment.id,
        riego.estado == False,
    ).order_by(riego.id.desc()).first()

    if session:
        session.duracion_segundos = max(int((now - session.fecha).total_seconds()), 1)
        session.estado = True
        session.motivo_cierre = reason
        db.add(session)

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
