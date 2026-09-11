from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.repositories import accessRep as data_repository


def require_assignment_access(db: Session, current_user, assignment_id: int):
    user_id = None if current_user.id_rol == 1 else current_user.id_usuario
    assignment = data_repository.queryAsignacion(db, assignment_id, user_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado"
        )
    return assignment


def require_crop_access(db: Session, current_user, crop_id: int):
    user_id = None if current_user.id_rol == 1 else current_user.id_usuario
    crop = data_repository.queryCultivo(db, crop_id, user_id)
    if not crop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado"
        )
    return crop


def require_telemetry_access(db: Session, current_user, telemetry_id: int):
    user_id = None if current_user.id_rol == 1 else current_user.id_usuario
    telemetry = data_repository.queryTelemetria(db, telemetry_id, user_id)
    if not telemetry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado"
        )
    return telemetry
