from sqlalchemy import func
from sqlalchemy.orm import Session

from src.main.model.models import (
    asignaciones_iot,
    configuracion_control,
    configuracion_tanque,
    ejecucion_riego,
    fuentes_agua,
    riego,
    telemetria_tanque,
)


def queryGetMaxRelaySecondsConfig(db: Session, user_id, crop_id):
    return (
        db.query(configuracion_control)
        .filter(
            configuracion_control.id_usuario == user_id,
            configuracion_control.id_cultivo == crop_id,
        )
        .first()
    )


def queryFindPumpAssignmentResultado(db: Session, user_id, crop_id):
    return (
        db.query(asignaciones_iot)
        .join(
            configuracion_tanque,
            configuracion_tanque.id_asignacion == asignaciones_iot.id,
        )
        .filter(
            asignaciones_iot.id_usuario == user_id,
            asignaciones_iot.id_cultivo == crop_id,
            asignaciones_iot.activo == True,
        )
        .first()
    )


def queryIsPausedSessionStartswith(session: Session):
    return session.motivo_cierre.startswith("pausado_")


def queryFindSensorAssignmentIdAsig(db: Session, pump_assignment_id):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id == pump_assignment_id)
        .first()
    )


def queryFindSensorAssignmentIdSensorAsig(db: Session, asig):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_dispositivo == asig.id_dispositivo,
            asignaciones_iot.id_tipo_metrica == 5,
        )
        .first()
    )


def queryFindSensorAssignmentIdSensorAsig2(db: Session, asig):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id_dispositivo == asig.id_dispositivo)
        .order_by(asignaciones_iot.id_tipo_metrica.desc().nullslast())
        .first()
    )


def queryStartNewExecutionLastTel(db: Session, sensor_id):
    return (
        db.query(telemetria_tanque)
        .filter(telemetria_tanque.id_asignacion == sensor_id)
        .order_by(telemetria_tanque.id.desc())
        .first()
    )


def queryCloseActiveExecutionExecution(db: Session, session: Session):
    return (
        db.query(ejecucion_riego)
        .filter(
            ejecucion_riego.id_riego == session.id, ejecucion_riego.fecha_fin.is_(None)
        )
        .order_by(ejecucion_riego.id.desc())
        .first()
    )


def queryCloseActiveExecutionLastTel(db: Session, sensor_id):
    return (
        db.query(telemetria_tanque)
        .filter(telemetria_tanque.id_asignacion == sensor_id)
        .order_by(telemetria_tanque.id.desc())
        .first()
    )


def queryCloseActiveExecutionAsig(db: Session, session: Session):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id == session.id_asignacion)
        .first()
    )


def queryCloseActiveExecutionFuente(db: Session, asig):
    return db.query(fuentes_agua).filter(fuentes_agua.id == asig.id_fuente_agua).first()


def queryPublishPumpStatusAsig(db: Session, session: Session):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id == session.id_asignacion)
        .first()
    )


def queryPauseIrrigationSessionEjecucionRiego(db: Session, session: Session):
    return (
        db.query(func.sum(ejecucion_riego.duracion_segundos))
        .filter(ejecucion_riego.id_riego == session.id)
        .scalar()
    )


def queryPauseIrrigationSessionEjecucionRiego2(db: Session, session: Session):
    return (
        db.query(func.sum(ejecucion_riego.cantidad_agua_litros))
        .filter(ejecucion_riego.id_riego == session.id)
        .scalar()
    )


def queryCompleteIrrigationSessionEjecucionRiego(db: Session, session: Session):
    return (
        db.query(func.sum(ejecucion_riego.duracion_segundos))
        .filter(ejecucion_riego.id_riego == session.id)
        .scalar()
    )


def queryCompleteIrrigationSessionEjecucionRiego2(db: Session, session: Session):
    return (
        db.query(func.sum(ejecucion_riego.cantidad_agua_litros))
        .filter(ejecucion_riego.id_riego == session.id)
        .scalar()
    )


def queryResumeIrrigationTankConfig(db: Session, assignment):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == assignment.id)
        .first()
    )


def queryResumeIrrigationSession(db: Session, assignment):
    return (
        db.query(riego)
        .filter(
            riego.id_asignacion == assignment.id,
            riego.estado == False,
            riego.motivo_cierre.like("pausado_%"),
        )
        .order_by(riego.id.desc())
        .first()
    )


def queryResumeIrrigationTankConfig2(db: Session, assignment):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == assignment.id)
        .first()
    )


def queryStartIrrigationTankConfig(db: Session, assignment):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == assignment.id)
        .first()
    )


def queryStartIrrigationActive(db: Session, assignment):
    return (
        db.query(riego)
        .filter(riego.id_asignacion == assignment.id, riego.estado == False)
        .order_by(riego.id.desc())
        .first()
    )


def queryStartIrrigationTankConfig2(db: Session, assignment):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == assignment.id)
        .first()
    )


def queryStartIrrigationTankConfig3(db: Session, assignment):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == assignment.id)
        .first()
    )


def queryStopIrrigationSession(db: Session, assignment):
    session = (
        db.query(riego)
        .filter(riego.id_asignacion == assignment.id, riego.estado == False)
        .order_by(riego.id.desc())
        .first()
    )
    if not session and getattr(assignment, "id_cultivo", None):
        session = (
            db.query(riego)
            .join(asignaciones_iot, asignaciones_iot.id == riego.id_asignacion)
            .filter(
                asignaciones_iot.id_cultivo == assignment.id_cultivo,
                riego.estado == False,
            )
            .order_by(riego.id.desc())
            .first()
        )
    return session


def queryStopIrrigationTankConfig(db: Session, assignment):
    return (
        db.query(configuracion_tanque)
        .filter(configuracion_tanque.id_asignacion == assignment.id)
        .first()
    )


def queryGetLitrosAcumuladosAsignacion(db: Session, id_asignacion: int) -> float:
    total_riego = (
        db.query(func.coalesce(func.sum(riego.cantidad_agua_litros), 0.0))
        .filter(riego.id_asignacion == id_asignacion)
        .scalar()
    )
    max_telemetria = (
        db.query(func.coalesce(func.max(telemetria_tanque.litros_acumulados), 0.0))
        .filter(telemetria_tanque.id_asignacion == id_asignacion)
        .scalar()
    )
    return float(max(float(total_riego or 0.0), float(max_telemetria or 0.0)))

