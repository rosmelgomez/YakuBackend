from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...services.repositories import telemetria as telemetria_repository
from ...db.models import (
    dispositivos,
    componentes,
    asignaciones_iot,
    humedad_suelo,
    humedad_ambiente,
    temperatura_ambiente,
    temperatura_suelo,
    telemetria_tanque,
)
from ...schemas.telemetria import TelemetriaTanqueModel, RiegoDatosModel
from .auth import get_current_user
from ..dependencies import get_db

router = APIRouter(prefix="/riego", tags=["Riego"])



def verificar_acceso_asignaciones(db: Session, asignacion_ids: List[int], current_user) -> None:
    for asig_id in asignacion_ids:
        # Buscar asignación activa
        asig = db.query(asignaciones_iot).filter(
            asignaciones_iot.id == asig_id,
            asignaciones_iot.activo == True
        ).first()
        
        if asig:
            # 1. Validación de Propiedad (solo si no es administrador)
            if current_user.id_rol != 1 and asig.id_usuario != current_user.id_usuario:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No tienes permiso para interactuar con la asignación '{asig_id}'",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asignación IoT con ID '{asig_id}' no encontrada o inactiva.",
            )


@router.post("/datos")
def guardar_datos_riego(
    data: RiegoDatosModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    verificar_acceso_asignaciones(db, [
        data.humedad_suelo.id_asignacion,
        data.humedad_ambiente.id_asignacion,
        data.temperatura_ambiente.id_asignacion,
        data.temperatura_suelo.id_asignacion
    ], current_user)

    try:
        telemetria_repository.crear_datos_riego(db, data)
        return {"status": "ok", "message": "Datos de riego guardados correctamente"}
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al guardar los datos de riego") from exc


@router.get("/lista_humedad_suelo")
def obtener_humedad_suelo(
    id_usuario: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Si no es admin, forzar su propio id_usuario para seguridad
    if current_user.id_rol != 1:
        id_usuario = current_user.id_usuario

    if id_usuario is not None:
        user_assignments = db.query(asignaciones_iot.id).filter(asignaciones_iot.id_usuario == id_usuario).subquery()
        return db.query(humedad_suelo).filter(humedad_suelo.id_asignacion.in_(user_assignments)).order_by(humedad_suelo.id.desc()).all()
    
    return telemetria_repository.listar_humedad_suelo(db)


@router.get("/lista_humedad_ambiente")
def obtener_humedad_ambiente(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Seguridad: Filtrar telemetría según asignaciones del usuario
    if current_user.id_rol != 1:
        user_assignments = db.query(asignaciones_iot.id).filter(asignaciones_iot.id_usuario == current_user.id_usuario).subquery()
        return db.query(humedad_ambiente).filter(humedad_ambiente.id_asignacion.in_(user_assignments)).order_by(humedad_ambiente.id.desc()).all()

    return telemetria_repository.listar_humedad_ambiente(db)


@router.get("/lista_temperatura_ambiente")
def obtener_temperatura_ambiente(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Seguridad: Filtrar telemetría según asignaciones del usuario
    if current_user.id_rol != 1:
        user_assignments = db.query(asignaciones_iot.id).filter(asignaciones_iot.id_usuario == current_user.id_usuario).subquery()
        return db.query(temperatura_ambiente).filter(temperatura_ambiente.id_asignacion.in_(user_assignments)).order_by(temperatura_ambiente.id.desc()).all()

    return telemetria_repository.listar_temperatura_ambiente(db)


@router.get("/lista_temperatura_suelo")
def obtener_temperatura_suelo(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Seguridad: Filtrar telemetría según asignaciones del usuario
    if current_user.id_rol != 1:
        user_assignments = db.query(asignaciones_iot.id).filter(asignaciones_iot.id_usuario == current_user.id_usuario).subquery()
        return db.query(temperatura_suelo).filter(temperatura_suelo.id_asignacion.in_(user_assignments)).order_by(temperatura_suelo.id.desc()).all()

    return telemetria_repository.listar_temperatura_suelo(db)


@router.post("/control_agua")
def guardar_control_agua(
    data: TelemetriaTanqueModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    verificar_acceso_asignaciones(db, [data.id_asignacion], current_user)

    try:
        registro = telemetria_repository.crear_telemetria_tanque(
            db=db,
            id_asignacion=data.id_asignacion,
            distancia_cm=data.distancia_cm,
            estado_bomba=data.estado_bomba,
            motivo_cierre=data.motivo_cierre,
            fecha=data.fecha,
        )
        return {
            "status": "ok",
            "message": "Telemetría de tanque guardada correctamente",
            "id": registro.id,
            "nivel_agua_cm": registro.nivel_agua_cm,
            "porcentaje_nivel": registro.porcentaje_nivel,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Error interno del servidor") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al guardar la telemetría del tanque") from exc


@router.get("/lista_control_agua")
def obtener_control_agua(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Seguridad: Filtrar telemetría según asignaciones del usuario
    if current_user.id_rol != 1:
        user_assignments = db.query(asignaciones_iot.id).filter(asignaciones_iot.id_usuario == current_user.id_usuario).subquery()
        return db.query(telemetria_tanque).filter(telemetria_tanque.id_asignacion.in_(user_assignments)).order_by(telemetria_tanque.id.desc()).all()

    return telemetria_repository.listar_telemetria_tanque(db)
