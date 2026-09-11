from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.dashboardDto import (
    BombaToggleModel,
    HorarioCreateModel,
    HorarioToggleModel,
    HorarioUpdateModel,
    ModoOperacionModel,
    NotifConfigListModel,
    NotifConfigUpdateModel,
    RelayDurationUpdateModel,
    TelemetriaBombaToggleModel,
    UmbralesUpdateModel,
    ValvulaToggleModel,
)
from src.main.service import dashboardServ

router = APIRouter(tags=["Dashboard y Control"])


@router.get("/dashboard/data")
def get_dashboard_data(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    return dashboardServ.get_dashboard_dataServ(db=db, current_user=current_user)


@router.get("/dashboard/cultivos-base")
def get_cultivos_base(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    return dashboardServ.get_cultivos_baseServ(db=db, current_user=current_user)


@router.get("/dashboard/alertas")
def get_alertas_data_endpoint(
    idCultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.get_alertas_data_endpointServ(
        idCultivo=idCultivo, db=db, current_user=current_user
    )


@router.get("/dashboard/historico")
def get_historico_data_endpoint(
    idCultivo: int,
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.get_historico_data_endpointServ(
        idCultivo=idCultivo, dias=dias, db=db, current_user=current_user
    )


@router.get("/dashboard/ml")
def get_ml_dashboard_data_endpoint(
    idCultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.get_ml_dashboard_data_endpointServ(
        idCultivo=idCultivo, db=db, current_user=current_user
    )


@router.get("/control/data")
def get_control_data(
    idCultivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.get_control_dataServ(
        idCultivo=idCultivo, db=db, current_user=current_user
    )


@router.post("/control/modo")
def set_modo_operacion(
    data: ModoOperacionModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.set_modo_operacionServ(
        data=data, db=db, current_user=current_user
    )


@router.post("/control/bomba/toggle")
def toggle_bomba_manual(
    data: BombaToggleModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.toggle_bomba_manualServ(
        data=data, db=db, current_user=current_user
    )


@router.post("/control/valvula/toggle")
def toggle_valvula_manual(
    data: ValvulaToggleModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.toggle_valvula_manualServ(
        data=data, db=db, current_user=current_user
    )


@router.patch("/control/configuracion/rele")
def update_max_relay_duration(
    data: RelayDurationUpdateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.update_max_relay_durationServ(
        data=data, db=db, current_user=current_user
    )


@router.post("/control/horario")
def agregar_horario(
    data: HorarioCreateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.agregar_horarioServ(
        data=data, db=db, current_user=current_user
    )


@router.put("/control/horario/{id_horario}")
def editar_horario(
    id_horario: int,
    data: HorarioUpdateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.editar_horarioServ(
        id_horario=id_horario, data=data, db=db, current_user=current_user
    )


@router.put("/control/horario/{id_horario}/toggle")
def toggle_horario(
    id_horario: int,
    data: HorarioToggleModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.toggle_horarioServ(
        id_horario=id_horario, data=data, db=db, current_user=current_user
    )


@router.delete("/control/horario/{id_horario}")
def eliminar_horario(
    id_horario: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.eliminar_horarioServ(
        id_horario=id_horario, db=db, current_user=current_user
    )


@router.post("/control/bomba/toggle-by-telemetria")
def toggle_bomba_by_telemetria(
    data: TelemetriaBombaToggleModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.toggle_bomba_by_telemetriaServ(
        data=data, db=db, current_user=current_user
    )


@router.post("/control/umbrales")
def update_umbrales(
    data: UmbralesUpdateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.update_umbralesServ(
        data=data, db=db, current_user=current_user
    )


@router.get("/dashboard/alertas/config", response_model=NotifConfigListModel)
def get_notif_config(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    return dashboardServ.get_notif_configServ(db=db, current_user=current_user)


@router.post("/dashboard/alertas/config")
def update_notif_config(
    data: NotifConfigUpdateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.update_notif_configServ(
        data=data, db=db, current_user=current_user
    )
