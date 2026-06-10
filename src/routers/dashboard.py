from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import get_db
from ..core.bff_auth import get_current_user_or_bff
from ..services import dashboard as dashboard_service
from ..services import control as control_service

router = APIRouter(tags=["Dashboard y Control"])


class ModoOperacionModel(BaseModel):
    idCultivo: int
    idBomba: int
    modo: str  # 'manual', 'predictivo', 'programado'


class BombaToggleModel(BaseModel):
    idBomba: int
    encender: bool


class HorarioCreateModel(BaseModel):
    idBomba: int
    hora: str  # "HH:MM"
    duracionMin: int
    dias: List[bool]  # [lunes, martes, miercoles, jueves, viernes, sabado, domingo]
    nombre: str | None = None


class HorarioToggleModel(BaseModel):
    activo: bool


class TelemetriaBombaToggleModel(BaseModel):
    idTelemetria: int
    estado: bool


class UmbralUpdateItem(BaseModel):
    id: int
    min: float
    max: float


class UmbralesUpdateModel(BaseModel):
    idCultivo: int
    updates: List[UmbralUpdateItem]


@router.get("/dashboard/data")
def get_dashboard_data(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        return dashboard_service.obtener_datos_dashboard(db, current_user.id_usuario)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/alertas")
def get_alertas_data_endpoint(
    idCultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        return dashboard_service.obtener_datos_alertas(db, current_user.id_usuario, idCultivo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/historico")
def get_historico_data_endpoint(
    idCultivo: int,
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        return dashboard_service.obtener_datos_historico(db, current_user.id_usuario, idCultivo, dias)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/ml")
def get_ml_dashboard_data_endpoint(
    idCultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        return dashboard_service.obtener_datos_ml(db, current_user.id_usuario, idCultivo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/control/data")
def get_control_data(
    idCultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        return control_service.obtener_datos_control(
            db, current_user.id_usuario, idCultivo, current_user.id_rol
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/control/modo")
def set_modo_operacion(
    data: ModoOperacionModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    modo = data.modo.lower()
    if modo not in ["manual", "predictivo", "programado"]:
        raise HTTPException(
            status_code=400,
            detail="Modo inválido. Debe ser manual, predictivo o programado.",
        )
    try:
        return control_service.establecer_modo_operacion(
            db, current_user.id_usuario, data.idBomba, data.modo, data.idCultivo
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/control/bomba/toggle")
def toggle_bomba_manual(
    data: BombaToggleModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        return control_service.conmutar_bomba_manual(
            db, current_user.id_usuario, data.idBomba, data.encender
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/control/horario")
def agregar_horario(
    data: HorarioCreateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        return control_service.crear_horario_riego(
            db,
            current_user.id_usuario,
            data.idBomba,
            data.hora,
            data.duracionMin,
            data.dias,
            data.nombre,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/control/horario/{id_horario}/toggle")
def toggle_horario(
    id_horario: int,
    data: HorarioToggleModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        res = control_service.conmutar_horario_riego(
            db, current_user.id_usuario, id_horario, data.activo
        )
        if res is None:
            raise HTTPException(status_code=404, detail="Horario no encontrado.")
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/control/horario/{id_horario}")
def eliminar_horario(
    id_horario: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        res = control_service.eliminar_horario_riego(
            db, current_user.id_usuario, id_horario
        )
        if res is None:
            raise HTTPException(status_code=404, detail="Horario no encontrado.")
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/control/bomba/toggle-by-telemetria")
def toggle_bomba_by_telemetria(
    data: TelemetriaBombaToggleModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        res = control_service.conmutar_bomba_por_telemetria(
            db, current_user.id_usuario, data.idTelemetria, data.estado
        )
        if res is None:
            raise HTTPException(
                status_code=404, detail="Registro de telemetría no encontrado"
            )
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/control/umbrales")
def update_umbrales(
    data: UmbralesUpdateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        return control_service.actualizar_umbrales_riego(
            db, current_user.id_usuario, data.idCultivo, data.updates
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
