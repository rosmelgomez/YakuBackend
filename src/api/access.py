from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..db.models import asignaciones_iot, cultivos, telemetria_tanque


def require_assignment_access(db: Session, current_user, assignment_id: int):
    query = db.query(asignaciones_iot).filter(asignaciones_iot.id == assignment_id)
    if current_user.id_rol != 1:
        query = query.filter(asignaciones_iot.id_usuario == current_user.id_usuario)
    assignment = query.first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")
    return assignment


def require_crop_access(db: Session, current_user, crop_id: int):
    query = db.query(cultivos).filter(cultivos.id_cultivo == crop_id)
    if current_user.id_rol != 1:
        query = query.filter(cultivos.id_usuario == current_user.id_usuario)
    crop = query.first()
    if not crop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")
    return crop


def require_telemetry_access(db: Session, current_user, telemetry_id: int):
    query = db.query(telemetria_tanque).join(
        asignaciones_iot,
        asignaciones_iot.id == telemetria_tanque.id_asignacion,
    ).filter(telemetria_tanque.id == telemetry_id)
    if current_user.id_rol != 1:
        query = query.filter(asignaciones_iot.id_usuario == current_user.id_usuario)
    telemetry = query.first()
    if not telemetry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado")
    return telemetry
