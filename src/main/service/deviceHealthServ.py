import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.main.model.models import (
    asignaciones_iot,
    dispositivos,
    logs_sistema,
)
from src.main.repositories import deviceHealthRep as data_repository
from src.main.repositories import sessionRep as session_repository
from src.main.service.irrigationServ import stop_irrigation

logger = logging.getLogger(__name__)

DEVICE_OFFLINE_TIMEOUT_SECONDS = int(os.getenv("DEVICE_OFFLINE_TIMEOUT_SECONDS", "130"))


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _tipo_nombre(device: dispositivos) -> str:
    return (device.tipo.nombre if device.tipo else "").lower()


def _is_sensor_device(device: dispositivos) -> bool:
    if getattr(device, "metodo_medicion", None) in ("proximidad", "flujometro"):
        return False
    name = _tipo_nombre(device)
    return device.id_tipo == 1 or any(
        word in name for word in ("sensor", "sensores", "captura", "colector")
    )


def _is_actuator_device(device: dispositivos) -> bool:
    if getattr(device, "metodo_medicion", None) in ("proximidad", "flujometro"):
        return True
    name = _tipo_nombre(device)
    return device.id_tipo == 2 or any(
        word in name for word in ("actuador", "riego", "tanque", "nivel")
    )


def touch_device_ping(
    db: Session, device: dispositivos | None, when: datetime | None = None
) -> None:
    if not device:
        return
    device.ultimo_ping = when or utc_now_naive()
    session_repository.add(db, device)
    session_repository.commit(db)


def touch_device_by_assignment(
    db: Session, assignment_id: int | None, when: datetime | None = None
) -> None:
    if not assignment_id:
        return
    assignment = data_repository.queryTouchDeviceByAssignmentAssignment(
        db, assignment_id
    )
    if assignment:
        touch_device_ping(db, assignment.dispositivo, when)


def _deactivate_device_assignments(
    db: Session, device: dispositivos, reason: str, now: datetime
) -> list[asignaciones_iot]:
    active_assignments = [
        assignment for assignment in device.asignaciones if assignment.activo
    ]
    if not active_assignments:
        return []

    for assignment in active_assignments:
        assignment.activo = False
        session_repository.add(db, assignment)

    session_repository.add(
        db,
        logs_sistema(
            id_usuario=active_assignments[0].id_usuario,
            accion="Dispositivo sin respuesta",
            modulo="Monitoreo IoT",
            descripcion=f"Se desactivo logicamente el dispositivo {device.nombre} por falta de respuesta ({reason}).",
            fecha=now,
        ),
    )
    return active_assignments


def _shutdown_actuator_state(
    db: Session, assignment: asignaciones_iot, reason: str
) -> None:
    config = data_repository.queryShutdownActuatorStateConfig(db, assignment)
    if config:
        config.bomba_encendida = False
        config.valvula_abierta = False
        config.actualizado_en = utc_now_naive()
        session_repository.add(db, config)

    active_session = data_repository.queryShutdownActuatorStateActiveSession(
        db, assignment
    )
    if active_session:
        try:
            stop_irrigation(db, assignment, reason, publish=False)
            try:
                from src.main.service.notifications.alertEngineServ import notificar_problema_riego
                notificar_problema_riego(
                    db,
                    assignment.id_usuario,
                    "Desconexión durante el riego",
                    f"Se detectó desconexión del equipo durante un riego activo ({reason}). El ciclo fue suspendido preventivamente.",
                    severidad="critica",
                )
            except Exception as notif_err:
                logger.warning(f"No se pudo enviar notificación de desconexión: {notif_err}")
        except Exception:
            session_repository.rollback(db)
            logger.exception("Error cerrando riego activo de dispositivo sin respuesta")


def _deactivate_crop_actuators(
    db: Session, user_id: int, crop_id: int | None, reason: str, now: datetime
) -> None:
    if crop_id is None:
        return

    actuator_assignments = (
        data_repository.queryDeactivateCropActuatorsActuatorAssignments(
            db, user_id, crop_id
        )
    )

    for assignment in actuator_assignments:
        device = assignment.dispositivo
        if not device or not _is_actuator_device(device):
            continue

        assignment.activo = False
        session_repository.add(db, assignment)
        _shutdown_actuator_state(db, assignment, reason)
        session_repository.add(
            db,
            logs_sistema(
                id_usuario=user_id,
                accion="Actuador desactivado por captura offline",
                modulo="Monitoreo IoT",
                descripcion=f"Se desactivo el actuador {device.nombre} porque el dispositivo de captura del cultivo dejo de responder.",
                fecha=now,
            ),
        )


def sync_device_health(db: Session, now: datetime | None = None) -> int:
    now = now or utc_now_naive()
    cutoff = now - timedelta(seconds=DEVICE_OFFLINE_TIMEOUT_SECONDS)
    affected = 0

    stale_devices = data_repository.querySyncDeviceHealthStaleDevices(db, cutoff)

    # Exclude actuator devices from automatic timeout deactivation, as they are silent when idle.
    stale_devices = [d for d in stale_devices if not _is_actuator_device(d)]

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
        session_repository.commit(db)
        logger.info(
            "[DEVICE HEALTH] Asignaciones desactivadas por timeout: %s", affected
        )

    return affected
