from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.service import monitoreoServ

router = APIRouter(prefix="/monitoreo", tags=["Monitoreo de Red y Auditoría"])


@router.get("/red")
def monitoreo_red(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Estado de conexión (En línea / Fuera de línea) de cada nodo IoT. Solo administradores."""
    return monitoreoServ.listar_monitoreo_redServ(db=db, current_user=current_user)


@router.get("/auditoria-eventos")
def auditoria_eventos(
    id_cultivo: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Eventos de riego con la decisión de la IA cruzada con el volumen medido."""
    return monitoreoServ.listar_auditoria_eventosServ(
        db=db, current_user=current_user, id_cultivo=id_cultivo, limit=limit
    )
