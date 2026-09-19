from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.permisoDto import PermisoResponse, PermisosUsuarioUpdate
from src.main.service import permisoServ

router = APIRouter(prefix="/admin", tags=["Permisos"])


@router.get("/permisos", response_model=List[PermisoResponse])
def listar_catalogo_permisos(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Catálogo completo de permisos granulares asignables (HU-31)."""
    return permisoServ.listar_catalogo_permisosServ(db=db, current_user=current_user)


@router.get("/usuarios/{id_usuario}/permisos", response_model=List[PermisoResponse])
def listar_permisos_usuario(
    id_usuario: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Permisos granulares actualmente otorgados a un usuario."""
    return permisoServ.listar_permisos_usuarioServ(
        id_usuario=id_usuario, db=db, current_user=current_user
    )


@router.put("/usuarios/{id_usuario}/permisos", response_model=List[PermisoResponse])
def asignar_permisos_usuario(
    id_usuario: int,
    payload: PermisosUsuarioUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Reemplaza el conjunto de permisos granulares de un usuario. Solo administradores."""
    return permisoServ.asignar_permisos_usuarioServ(
        id_usuario=id_usuario,
        codigos=payload.codigos,
        db=db,
        current_user=current_user,
    )
