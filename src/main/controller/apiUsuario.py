from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.dashboardDto import AdminDashboardSummaryResponse
from src.main.dtos.usuarioDto import AdminUserCreateInput, UsuarioAdminResponse
from src.main.service import usuarioServ

router = APIRouter(prefix="/admin", tags=["Administración"])


@router.post("/usuarios", status_code=status.HTTP_201_CREATED)
def crear_usuario_administrativo(
    data: AdminUserCreateInput,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return usuarioServ.crear_usuario_administrativoServ(
        data=data, db=db, current_user=current_user
    )


@router.get("/usuarios", response_model=List[UsuarioAdminResponse])
def listar_usuarios_sistema(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """
    Lista todos los usuarios registrados en el sistema.
    Solo accesible por administradores (id_rol = 1).
    """
    return usuarioServ.listar_usuarios_sistemaServ(db=db, current_user=current_user)


@router.post("/usuarios/{id_usuario}/estado/{estado}")
def cambiar_estado_usuario(
    id_usuario: int,
    estado: bool,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return usuarioServ.cambiar_estado_usuarioServ(
        id_usuario=id_usuario, estado=estado, db=db, current_user=current_user
    )


@router.post("/usuarios/{id_usuario}/rol/{id_rol}")
def cambiar_rol_usuario(
    id_usuario: int,
    id_rol: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return usuarioServ.cambiar_rol_usuarioServ(
        id_usuario=id_usuario, id_rol=id_rol, db=db, current_user=current_user
    )


@router.get("/resumen", response_model=AdminDashboardSummaryResponse)
def admin_resumen_dashboard(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """
    Consolida métricas, logs, predicciones de ML y consumos globales para el administrador.
    Solo accesible por administradores (id_rol = 1).
    """
    return usuarioServ.admin_resumen_dashboardServ(db=db, current_user=current_user)
