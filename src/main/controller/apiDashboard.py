from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.dashboardDto import (
    CooldownUpdateModel,
    NotifConfigListModel,
    NotifConfigUpdateModel,
    RelayDurationUpdateModel,
    TelemetriaBombaToggleModel,
    UmbralesUpdateModel,
)
from src.main.service import dashboardServ

router = APIRouter(tags=["Dashboard y Control"])


@router.get("/dashboard/data")
def get_dashboard_data(
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
    return dashboardServ.get_dashboard_dataServ(db=db, current_user=current_user)


@router.get("/dashboard/cultivos-base")
def get_cultivos_base(
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    response.headers["Cache-Control"] = "private, max-age=60, stale-while-revalidate=120"
    return dashboardServ.get_cultivos_baseServ(db=db, current_user=current_user)


@router.get("/dashboard/alertas")
def get_alertas_data_endpoint(
    idCultivo: int,
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
    return dashboardServ.get_alertas_data_endpointServ(
        idCultivo=idCultivo, db=db, current_user=current_user
    )


@router.get("/dashboard/historico")
def get_historico_data_endpoint(
    idCultivo: int,
    response: Response,
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    response.headers["Cache-Control"] = "private, max-age=60, stale-while-revalidate=120"
    return dashboardServ.get_historico_data_endpointServ(
        idCultivo=idCultivo, dias=dias, db=db, current_user=current_user
    )


@router.get("/dashboard/ml")
def get_ml_dashboard_data_endpoint(
    idCultivo: int,
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    response.headers["Cache-Control"] = "private, max-age=60, stale-while-revalidate=120"
    return dashboardServ.get_ml_dashboard_data_endpointServ(
        idCultivo=idCultivo, db=db, current_user=current_user
    )


@router.get("/control/data")
def get_control_data(
    idCultivo: int,
    response: Response,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    response.headers["Cache-Control"] = "private, max-age=10, stale-while-revalidate=20"
    return dashboardServ.get_control_dataServ(
        idCultivo=idCultivo, db=db, current_user=current_user
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


@router.patch("/control/configuracion/cooldown")
def update_cooldown(
    data: CooldownUpdateModel,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return dashboardServ.update_cooldownServ(
        data=data, db=db, current_user=current_user
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
