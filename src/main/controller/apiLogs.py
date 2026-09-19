from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.logDto import LogSistemaResponse
from src.main.service import logServ

router = APIRouter(prefix="/admin/logs", tags=["Auditoría"])


@router.get("", response_model=List[LogSistemaResponse])
def listar_logs_sistema(
    modulo: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Historial de auditoría del sistema: mantenimiento técnico (HU-25), inicios
    de sesión y cambios de permisos (HU-32), y errores de red MQTT (HU-35)."""
    return logServ.listar_logs_sistemaServ(
        db=db,
        modulo=modulo,
        desde=desde,
        hasta=hasta,
        limit=limit,
        current_user=current_user,
    )
