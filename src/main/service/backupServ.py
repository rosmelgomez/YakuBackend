"""Autorización y preparación de descargas de respaldo."""

import io

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.main.repositories import backupRep


def descargar_backup_dbServ(db: Session = None, current_user=None):
    from src.main.service.permisoServ import require_permiso

    require_permiso(db, current_user, "GESTIONAR_RESPALDOS")
    try:
        sql_content, filename = backupRep.exportarBackup(db)
    except backupRep.BackupError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible generar la copia de seguridad",
        ) from exc
    return StreamingResponse(
        io.BytesIO(sql_content.encode("utf-8")),
        media_type="application/sql",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
