from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.main.core.authDependencies import get_current_user
from src.main.core.dependencies import get_db
from src.main.dtos.telemetriaDto import RiegoDatosModel, TelemetriaTanqueModel
from src.main.service import telemetriaServ

router = APIRouter(prefix="/riego", tags=["Riego"])


@router.post("/datos")
def guardar_datos_riego(
    data: RiegoDatosModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return telemetriaServ.guardar_datos_riegoServ(
        data=data, db=db, current_user=current_user
    )


@router.get("/lista_humedad_suelo")
def obtener_humedad_suelo(
    id_usuario: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return telemetriaServ.obtener_humedad_sueloServ(
        id_usuario=id_usuario, db=db, current_user=current_user
    )


@router.get("/lista_humedad_ambiente")
def obtener_humedad_ambiente(
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    return telemetriaServ.obtener_humedad_ambienteServ(db=db, current_user=current_user)


@router.get("/lista_temperatura_ambiente")
def obtener_temperatura_ambiente(
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    return telemetriaServ.obtener_temperatura_ambienteServ(
        db=db, current_user=current_user
    )


@router.get("/lista_temperatura_suelo")
def obtener_temperatura_suelo(
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    return telemetriaServ.obtener_temperatura_sueloServ(
        db=db, current_user=current_user
    )


@router.post("/control_agua")
def guardar_control_agua(
    data: TelemetriaTanqueModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return telemetriaServ.guardar_control_aguaServ(
        data=data, db=db, current_user=current_user
    )


@router.get("/lista_control_agua")
def obtener_control_agua(
    db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    return telemetriaServ.obtener_control_aguaServ(db=db, current_user=current_user)
