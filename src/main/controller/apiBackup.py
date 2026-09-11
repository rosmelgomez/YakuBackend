from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.service import backupServ

router = APIRouter(prefix="/admin/backup", tags=["Administración Backup"])


@router.get("")
def descargar_backup_db(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """
    Genera un backup en formato SQL de la base de datos y lo expone como descarga.
    Solo accesible por administradores (id_rol = 1).
    """
    return backupServ.descargar_backup_dbServ(db=db, current_user=current_user)
