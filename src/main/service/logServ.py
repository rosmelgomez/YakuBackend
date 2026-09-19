"""Consulta del historial de auditoría del sistema (logs_sistema)."""

from datetime import datetime

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
    """Lista el historial de auditoría del sistema registrado en logs_sistema:
    mantenimiento técnico (calibraciones, desconexiones), autenticación
    (inicios de sesión fallidos/exitosos), cambios de rol/permisos y errores de
    red MQTT. Filtra por `modulo` para acotar a una categoría (HU-25/HU-32/HU-35)."""
    from src.main.service.permisoServ import require_permiso

    require_permiso(db, current_user, "VER_AUDITORIA")

    query = db.query(logs_sistema)
    if modulo:
        query = query.filter(logs_sistema.modulo == modulo)
    if desde is not None:
        query = query.filter(logs_sistema.fecha >= desde)
    if hasta is not None:
        query = query.filter(logs_sistema.fecha <= hasta)

    return query.order_by(logs_sistema.fecha.desc()).limit(limit).all()
