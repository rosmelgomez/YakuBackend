"""Consulta del historial de mantenimiento técnico (logs_sistema)."""

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.model.models import logs_sistema


def listar_logs_sistemaServ(
    db: Session,
    modulo: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limit: int = 100,
    current_user=None,
):
    """Lista el historial de acciones de mantenimiento/técnicas registradas en
    logs_sistema (calibraciones, desconexiones, desactivaciones, etc). Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para consultar el historial.",
        )

    query = db.query(logs_sistema)
    if modulo:
        query = query.filter(logs_sistema.modulo == modulo)
    if desde is not None:
        query = query.filter(logs_sistema.fecha >= desde)
    if hasta is not None:
        query = query.filter(logs_sistema.fecha <= hasta)

    return query.order_by(logs_sistema.fecha.desc()).limit(limit).all()
