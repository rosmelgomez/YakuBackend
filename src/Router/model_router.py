from typing import Generator
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..Model import crud
from ..Model.conexion import SessionLocal
from ..Model.model import (
    dispositivos,
    sensores,
    humedad_suelo,
    humedad_ambiente,
    temperatura_ambiente,
    temperatura_suelo,
    telemetria_tanque,
)
from ..Model.schemas import TelemetriaTanqueModel, RiegoDatosModel
from .auth_router import get_current_user

router = APIRouter(prefix="/riego", tags=["Riego"])


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verificar_acceso_sensores(db: Session, sensor_names: list[str], current_user) -> None:
    for name in sensor_names:
        sensor_db = db.query(sensores).filter(sensores.nombre == name).first()
        if sensor_db:
            dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == sensor_db.id_dispositivo).first()
            if dispositivo:
                # 1. Validación de Propiedad (solo si no es administrador)
                if current_user.id_rol != 1 and dispositivo.id_usuario != current_user.id_usuario:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"No tienes permiso para interactuar con el sensor '{name}'",
                    )
                # 2. Validación de Funcionamiento Activo
                if not dispositivo.funcionamiento_activo:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"El dispositivo '{dispositivo.nombre}' tiene el funcionamiento desactivado por el usuario.",
                    )


@router.post("/datos")
def guardar_datos_riego(
    data: RiegoDatosModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    verificar_acceso_sensores(db, [
        data.humedad_suelo.sensor,
        data.humedad_ambiente.sensor,
        data.temperatura_ambiente.sensor,
        data.temperatura_suelo.sensor
    ], current_user)

    # Buscar un dispositivo del usuario para mapear sensores nuevos
    dispositivo = db.query(dispositivos).filter(dispositivos.id_usuario == current_user.id_usuario).first()
    id_dispositivo = dispositivo.id_dispositivo if dispositivo else None

    try:
        crud.crear_datos_riego(db, data, id_dispositivo=id_dispositivo)
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
        user_devices = db.query(dispositivos.id_dispositivo).filter(dispositivos.id_usuario == id_usuario).subquery()
        user_sensors = db.query(sensores.id_sensor).filter(sensores.id_dispositivo.in_(user_devices)).subquery()
        return db.query(humedad_suelo).filter(humedad_suelo.id_sensor.in_(user_sensors)).order_by(humedad_suelo.id.desc()).all()
    
    return crud.listar_humedad_suelo(db)


@router.get("/lista_humedad_ambiente")
def obtener_humedad_ambiente(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Seguridad: Filtrar telemetría según dispositivos asignados
    if current_user.id_rol != 1:
        user_devices = db.query(dispositivos.id_dispositivo).filter(dispositivos.id_usuario == current_user.id_usuario).subquery()
        user_sensors = db.query(sensores.id_sensor).filter(sensores.id_dispositivo.in_(user_devices)).subquery()
        return db.query(humedad_ambiente).filter(humedad_ambiente.id_sensor.in_(user_sensors)).order_by(humedad_ambiente.id.desc()).all()

    return crud.listar_humedad_ambiente(db)


@router.get("/lista_temperatura_ambiente")
def obtener_temperatura_ambiente(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Seguridad: Filtrar telemetría según dispositivos asignados
    if current_user.id_rol != 1:
        user_devices = db.query(dispositivos.id_dispositivo).filter(dispositivos.id_usuario == current_user.id_usuario).subquery()
        user_sensors = db.query(sensores.id_sensor).filter(sensores.id_dispositivo.in_(user_devices)).subquery()
        return db.query(temperatura_ambiente).filter(temperatura_ambiente.id_sensor.in_(user_sensors)).order_by(temperatura_ambiente.id.desc()).all()

    return crud.listar_temperatura_ambiente(db)


@router.get("/lista_temperatura_suelo")
def obtener_temperatura_suelo(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Seguridad: Filtrar telemetría según dispositivos asignados
    if current_user.id_rol != 1:
        user_devices = db.query(dispositivos.id_dispositivo).filter(dispositivos.id_usuario == current_user.id_usuario).subquery()
        user_sensors = db.query(sensores.id_sensor).filter(sensores.id_dispositivo.in_(user_devices)).subquery()
        return db.query(temperatura_suelo).filter(temperatura_suelo.id_sensor.in_(user_sensors)).order_by(temperatura_suelo.id.desc()).all()

    return crud.listar_temperatura_suelo(db)


@router.post("/control_agua")
def guardar_control_agua(
    data: TelemetriaTanqueModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    verificar_acceso_sensores(db, [data.sensor], current_user)

    # Buscar un dispositivo del usuario para mapear sensores nuevos
    dispositivo = db.query(dispositivos).filter(dispositivos.id_usuario == current_user.id_usuario).first()
    id_dispositivo = dispositivo.id_dispositivo if dispositivo else None

    try:
        registro = crud.crear_telemetria_tanque(
            db=db,
            sensor=data.sensor,
            distancia_cm=data.distancia_cm,
            estado_bomba=data.estado_bomba,
            fecha=data.fecha,
            id_dispositivo=id_dispositivo,
        )
        return {
            "status": "ok",
            "message": "Telemetría de tanque guardada correctamente",
            "id": registro.id,
            "nivel_agua_cm": registro.nivel_agua_cm,
            "porcentaje_nivel": registro.porcentaje_nivel,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error al guardar la telemetría del tanque") from exc


@router.get("/lista_control_agua")
def obtener_control_agua(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Seguridad: Filtrar telemetría según dispositivos asignados
    if current_user.id_rol != 1:
        user_devices = db.query(dispositivos.id_dispositivo).filter(dispositivos.id_usuario == current_user.id_usuario).subquery()
        user_sensors = db.query(sensores.id_sensor).filter(sensores.id_dispositivo.in_(user_devices)).subquery()
        return db.query(telemetria_tanque).filter(telemetria_tanque.id_sensor.in_(user_sensors)).order_by(telemetria_tanque.id.desc()).all()

    return crud.listar_telemetria_tanque(db)
