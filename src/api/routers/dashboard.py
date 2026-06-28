from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ...core.bff_auth import get_current_user_or_bff
from ...services import dashboard as dashboard_service
from ...services import control as control_service
from ..access import require_assignment_access, require_crop_access, require_telemetry_access

router = APIRouter(tags=["Dashboard y Control"])


class ModoOperacionModel(BaseModel):
    idCultivo: int
    idBomba: int
    modo: str  # 'manual', 'predictivo', 'programado'


class BombaToggleModel(BaseModel):
    idBomba: int
    encender: bool


class ValvulaToggleModel(BaseModel):
    idBomba: int
    abrir: bool


class HorarioCreateModel(BaseModel):
    idBomba: int
    hora: str  # "HH:MM"
    duracionMin: int = Field(ge=1, le=30)
    dias: List[bool]  # [lunes, martes, miercoles, jueves, viernes, sabado, domingo]
    nombre: str | None = None


class HorarioToggleModel(BaseModel):
    activo: bool


class RelayDurationUpdateModel(BaseModel):
    idCultivo: int
    duracionMaxMinutos: int = Field(ge=1, le=30)


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
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/dashboard/alertas")
def get_alertas_data_endpoint(
    idCultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_crop_access(db, current_user, idCultivo)
    try:
        return dashboard_service.obtener_datos_alertas(db, current_user.id_usuario, idCultivo)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/dashboard/historico")
def get_historico_data_endpoint(
    idCultivo: int,
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_crop_access(db, current_user, idCultivo)
    try:
        return dashboard_service.obtener_datos_historico(db, current_user.id_usuario, idCultivo, dias)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/dashboard/ml")
def get_ml_dashboard_data_endpoint(
    idCultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_crop_access(db, current_user, idCultivo)
    try:
        return dashboard_service.obtener_datos_ml(db, current_user.id_usuario, idCultivo)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/control/data")
def get_control_data(
    idCultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_crop_access(db, current_user, idCultivo)
    try:
        return control_service.obtener_datos_control(
            db, current_user.id_usuario, idCultivo, current_user.id_rol
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


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
    require_assignment_access(db, current_user, data.idBomba)
    require_crop_access(db, current_user, data.idCultivo)
    try:
        return control_service.establecer_modo_operacion(
            db, current_user.id_usuario, data.idBomba, data.modo, data.idCultivo
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/control/bomba/toggle")
def toggle_bomba_manual(
    data: BombaToggleModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_assignment_access(db, current_user, data.idBomba)
    try:
        return control_service.conmutar_bomba_manual(
            db, current_user.id_usuario, data.idBomba, data.encender
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/control/valvula/toggle")
def toggle_valvula_manual(
    data: ValvulaToggleModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_assignment_access(db, current_user, data.idBomba)
    try:
        return control_service.conmutar_valvula_manual(
            db, current_user.id_usuario, data.idBomba, data.abrir
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.patch("/control/configuracion/rele")
def update_max_relay_duration(
    data: RelayDurationUpdateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_crop_access(db, current_user, data.idCultivo)
    try:
        return control_service.actualizar_tiempo_maximo_rele(
            db,
            current_user.id_usuario,
            data.idCultivo,
            data.duracionMaxMinutos,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/control/horario")
def agregar_horario(
    data: HorarioCreateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_assignment_access(db, current_user, data.idBomba)
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


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
        raise HTTPException(status_code=500, detail="Error interno del servidor")


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
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/control/bomba/toggle-by-telemetria")
def toggle_bomba_by_telemetria(
    data: TelemetriaBombaToggleModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_telemetry_access(db, current_user, data.idTelemetria)
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
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/control/umbrales")
def update_umbrales(
    data: UmbralesUpdateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    require_crop_access(db, current_user, data.idCultivo)
    try:
        return control_service.actualizar_umbrales_riego(
            db, current_user.id_usuario, data.idCultivo, data.updates
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


class NotifConfigItemModel(BaseModel):
    id_tipo_alerta: int
    nombre: str
    canal_email: bool
    canal_dashboard: bool
    recordatorio_minutos: int

class NotifConfigListModel(BaseModel):
    configs: List[NotifConfigItemModel]

class NotifConfigUpdateItem(BaseModel):
    id_tipo_alerta: int
    canal_email: bool
    canal_dashboard: bool
    recordatorio_minutos: int = Field(ge=5, le=1440)

class NotifConfigUpdateModel(BaseModel):
    updates: List[NotifConfigUpdateItem]


@router.get("/dashboard/alertas/config", response_model=NotifConfigListModel)
def get_notif_config(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        from ...db.models import tipos_alerta, configuracion_notificaciones
        
        tipos = db.query(tipos_alerta).filter(tipos_alerta.activo == True).order_by(tipos_alerta.id.asc()).all()
        
        configs = []
        for t in tipos:
            pref = db.query(configuracion_notificaciones).filter(
                configuracion_notificaciones.id_usuario == current_user.id_usuario,
                configuracion_notificaciones.id_tipo_alerta == t.id
            ).first()
            
            configs.append(NotifConfigItemModel(
                id_tipo_alerta=t.id,
                nombre=t.nombre,
                canal_email=pref.canal_email if pref else True,
                canal_dashboard=pref.canal_dashboard if pref else True,
                recordatorio_minutos=(
                    pref.recordatorio_minutos if pref and pref.recordatorio_minutos
                    else (15 if t.severidad in {"critico", "critica", "emergencia"} else 30)
                ),
            ))
            
        return NotifConfigListModel(configs=configs)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/dashboard/alertas/config")
def update_notif_config(
    data: NotifConfigUpdateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    try:
        from ...db.models import configuracion_notificaciones
        
        for u in data.updates:
            pref = db.query(configuracion_notificaciones).filter(
                configuracion_notificaciones.id_usuario == current_user.id_usuario,
                configuracion_notificaciones.id_tipo_alerta == u.id_tipo_alerta
            ).first()
            
            if pref:
                pref.canal_email = u.canal_email
                pref.canal_dashboard = u.canal_dashboard
                pref.recordatorio_minutos = u.recordatorio_minutos
            else:
                pref = configuracion_notificaciones(
                    id_usuario=current_user.id_usuario,
                    id_tipo_alerta=u.id_tipo_alerta,
                    canal_email=u.canal_email,
                    canal_dashboard=u.canal_dashboard,
                    recordatorio_minutos=u.recordatorio_minutos,
                    activo=True
                )
                db.add(pref)
                
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error interno del servidor")

