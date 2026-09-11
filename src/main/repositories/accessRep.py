"""Consultas de recursos limitadas al propietario solicitado."""

from sqlalchemy.orm import Session

from src.main.model.models import asignaciones_iot, cultivos, telemetria_tanque


def queryAsignacion(db: Session, assignment_id: int, user_id: int | None):
    query = db.query(asignaciones_iot).filter(asignaciones_iot.id == assignment_id)
    if user_id is not None:
        query = query.filter(asignaciones_iot.id_usuario == user_id)
    return query.first()


def queryCultivo(db: Session, crop_id: int, user_id: int | None):
    query = db.query(cultivos).filter(cultivos.id_cultivo == crop_id)
    if user_id is not None:
        query = query.filter(cultivos.id_usuario == user_id)
    return query.first()


def queryTelemetria(db: Session, telemetry_id: int, user_id: int | None):
    query = (
        db.query(telemetria_tanque)
        .join(asignaciones_iot, telemetria_tanque.id_asignacion == asignaciones_iot.id)
        .filter(telemetria_tanque.id == telemetry_id)
    )
    if user_id is not None:
        query = query.filter(asignaciones_iot.id_usuario == user_id)
    return query.first()
