from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..Model.model import usuarios, dispositivos
from ..Model.schemas import UsuarioResponseModel, DispositivoResponseModel
from .auth_router import get_current_user, get_db

router = APIRouter(prefix="/admin", tags=["Administración"])


@router.get("/usuarios", response_model=List[UsuarioResponseModel])
def listar_usuarios_sistema(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Lista todos los usuarios registrados en el sistema.
    Solo accesible por administradores (id_rol = 1).
    """
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )
    return db.query(usuarios).order_by(usuarios.id_usuario).all()



