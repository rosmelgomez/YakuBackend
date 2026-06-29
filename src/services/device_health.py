import logging
import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..db.models import (
    asignaciones_iot,
    configuracion_tanque,
    dispositivos,
    logs_sistema,
    programacion_riego,
    riego,
)
from .irrigation import stop_irrigation


logger = logging.getLogger(__name__)

DEVICE_OFFLINE_TIMEOUT_SECONDS = int(os.getenv("DEVICE_OFFLINE_TIMEOUT_SECONDS", "130"))


def _tipo_nombre(device: dispositivos) -> str:
    return (device.tipo.nombre if device.tipo else "").lower()


def _is_sensor_device(device: dispositivos) -> bool:
    name = _tipo_nombre(device)
    return device.id_tipo == 1 or any(word in name for word in ("sensor", "sensores", "captura", "colector"))


def _is_actuator_device(device: dispositivos) -> bool:
    name = _tipo_nombre(device)
    return device.id_tipo == 2 or any(word in name for word in ("actuador", "riego", "tanque", "nivel"))


def touch_device_ping(db: Session, device: dispositivos | None, when: datetime | None = None) -> None:
    if not device:
        return
    device.ultimo_ping = when or datetime.now()
    db.add(device)


def touch_device_by_assignment(db: Session, assignment_id: int | None, when: datetime | None = None) -> None:
    if not assignment_id:
        return
    assignment = db.query(asignaciones_iot).filter(asignaciones_iot.id == assignment_id).first()
    if assignment:
        touch_device_ping(db, assignment.dispositivo, when)


def _deactivate_device_assignments(db: Session, device: dispositivos, reason: str, now: datetime) -> list[asignaciones_iot]:
    active_assignments = [assignment for assignment in device.asignaciones if assignment.activo]
    if not active_assignments:
        return []

    for assignment in active_assignments:
        assignment.activo = False
        db.add(assignment)

    db.add(
        logs_sistema(
            id_usuario=active_assignments[0].id_usuario,
            accion="Dispositivo sin respuesta",
            modulo="Monitoreo IoT",
            descripcion=(
                f"Se desactivo logicamente el dispositivo {device.nombre} "
                f"por falta de respuesta ({reason})."
            ),
            fecha=now,
        )
    )
    return active_assignments


def _shutdown_actuator_state(db: Session, assignment: asignaciones_iot, reason: str) -> None:
    config = db.query(configuracion_tanque).filter(
        configuracion_tanque.id_asignacion == assignment.id
    ).first()
    if config:
        config.bomba_encendida = False
        config.valvula_abierta = False
        config.actualizado_en = datetime.now()
        db.add(config)

    active_session = db.query(riego).filter(
        riego.id_asignacion == assignment.id,
        riego.estado == False,
    ).first()
    if active_session:
        try:
            stop_irrigation(db, assignment, reason, publish=False)
        except Exception:
            db.rollback()
            logger.exception("Error cerrando riego activo de dispositivo sin respuesta")


def _deactivate_crop_actuators(db: Session, user_id: int, crop_id: int | None, reason: str, now: datetime) -> None:
    if crop_id is None:
        return

    actuator_assignments = db.query(asignaciones_iot).join(dispositivos).filter(
        asignaciones_iot.id_usuario == user_id,
        asignaciones_iot.id_cultivo == crop_id,
        asignaciones_iot.activo == True,
    ).all()

    for assignment in actuator_assignments:
        device = assignment.dispositivo
        if not device or not _is_actuator_device(device):
            continue

        assignment.activo = False
        db.add(assignment)
        _shutdown_actuator_state(db, assignment, reason)
        db.add(
            logs_sistema(
                id_usuario=user_id,
                accion="Actuador desactivado por captura offline",
                modulo="Monitoreo IoT",
                descripcion=(
                    f"Se desactivo el actuador {device.nombre} porque el dispositivo "
                    "de captura del cultivo dejo de responder."
                ),
                fecha=now,
            )
        )

    db.query(programacion_riego).filter(
        programacion_riego.id_usuario == user_id,
        programacion_riego.id_cultivo == crop_id,
        programacion_riego.activo == True,
    ).update({programacion_riego.activo: False}, synchronize_session=False)


def sync_device_health(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now()
    cutoff = now - timedelta(seconds=DEVICE_OFFLINE_TIMEOUT_SECONDS)
    affected = 0

    stale_devices = db.query(dispositivos).join(asignaciones_iot).filter(
        asignaciones_iot.activo == True,
        dispositivos.ultimo_ping.isnot(None),
        dispositivos.ultimo_ping < cutoff,
    ).distinct().all()

    for device in stale_devices:
        reason = f"ultimo ping {device.ultimo_ping}"
        active_assignments = _deactivate_device_assignments(db, device, reason, now)
        affected += len(active_assignments)

        for assignment in active_assignments:
            if _is_actuator_device(device):
                _shutdown_actuator_state(db, assignment, "dispositivo_offline")
            if _is_sensor_device(device):
                _deactivate_crop_actuators(
                    db,
                    assignment.id_usuario,
                    assignment.id_cultivo,
                    "captura_offline",
                    now,
                )

    if affected:
        db.commit()
        logger.info("[DEVICE HEALTH] Asignaciones desactivadas por timeout: %s", affected)

    return affected
