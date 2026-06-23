from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...db.models import almacenes, dispositivos, componentes
from ...schemas.almacen import AlmacenResponseModel, AlmacenCreate
from ...core.bff_auth import get_current_user_or_bff
from ..dependencies import get_db

router = APIRouter(prefix="/almacenes", tags=["Gestión de Almacenes"])



@router.get("", response_model=List[AlmacenResponseModel])
def listar_almacenes(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Obtiene el listado completo de almacenes."""
    return db.query(almacenes).order_by(almacenes.nombre.asc()).all()


@router.post("", response_model=AlmacenResponseModel, status_code=status.HTTP_201_CREATED)
def registrar_almacen(
    payload: AlmacenCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Registra un nuevo almacén. Solo accesible por administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    # Validar duplicados
    existente = db.query(almacenes).filter(almacenes.nombre == payload.nombre).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un almacén con este nombre."
        )

    nuevo = almacenes(
        nombre=payload.nombre,
        id_distrito=payload.id_distrito,
        direccion=payload.direccion
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.delete("/{almacen_id}", status_code=status.HTTP_200_OK)
def eliminar_almacen(
    almacen_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Elimina un almacén si no tiene dispositivos ni componentes asignados. Solo accesible por administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )

    alm = db.query(almacenes).filter(almacenes.id == almacen_id).first()
    if not alm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Almacén no encontrado."
        )

    # Verificar si tiene dispositivos en stock
    tiene_dispositivos = db.query(dispositivos).filter(dispositivos.id_almacen == almacen_id).first()
    if tiene_dispositivos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar el almacén porque contiene dispositivos asociados."
        )

    # Verificar si tiene componentes en stock
    tiene_componentes = db.query(componentes).filter(componentes.id_almacen == almacen_id).first()
    if tiene_componentes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar el almacén porque contiene componentes asociados."
        )

    db.delete(alm)
    db.commit()
    return {"status": "ok", "message": "Almacén eliminado correctamente."}
