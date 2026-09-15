from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.service import notificacionesServ

router = APIRouter(prefix="/notificaciones", tags=["Notificaciones"])


@router.get("")
def listar_notificaciones(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    return notificacionesServ.listar_notificacionesServ(db=db, current_user=current_user)


@router.post("/{id_alerta}/leida")
def marcar_leida(
    id_alerta: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return notificacionesServ.marcar_leidaServ(
        db=db, current_user=current_user, id_alerta=id_alerta
    )


@router.post("/marcar-todas-leidas")
def marcar_todas_leidas(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    return notificacionesServ.marcar_todas_leidasServ(db=db, current_user=current_user)


@router.delete("")
def limpiar_notificaciones(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    return notificacionesServ.limpiar_notificacionesServ(db=db, current_user=current_user)
