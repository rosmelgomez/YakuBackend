from sqlalchemy.orm import Session

from src.main.model.models import (
    asignaciones_iot,
    configuracion_tanque,
    dispositivos,
    riego,
)


def queryTouchDeviceByAssignmentAssignment(db: Session, assignment_id):
    return (
        db.query(asignaciones_iot).filter(asignaciones_iot.id == assignment_id).first()
    )


def queryShutdownActuatorStateConfig(db: Session, assignment):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == assignment.id)
        .first()
    )


def queryShutdownActuatorStateActiveSession(db: Session, assignment):
    return (
        db.query(riego)
        .filter(riego.id_asignacion == assignment.id, riego.estado == False)
        .first()
    )


def queryDeactivateCropActuatorsActuatorAssignments(db: Session, user_id, crop_id):
    return (
        db.query(asignaciones_iot)
        .join(dispositivos)
        .filter(
            asignaciones_iot.id_usuario == user_id,
            asignaciones_iot.id_cultivo == crop_id,
            asignaciones_iot.activo == True,
        )
        .all()
    )


def querySyncDeviceHealthStaleDevices(db: Session, cutoff):
    return (
        db.query(dispositivos)
        .join(asignaciones_iot)
        .filter(
            asignaciones_iot.activo == True,
            dispositivos.ultimo_ping.isnot(None),
            dispositivos.ultimo_ping < cutoff,
        )
        .distinct()
        .all()
    )
