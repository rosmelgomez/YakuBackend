from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.almacenDto import AlmacenCreate, AlmacenResponseModel
from src.main.service import almacenServ

router = APIRouter(prefix="/almacenes", tags=["Gestión de Almacenes"])


@router.get("", response_model=List[AlmacenResponseModel])
def listar_almacenes(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """Obtiene el listado completo de almacenes."""
    return almacenServ.listar_almacenesServ(db=db, current_user=current_user)


@router.post(
    "", response_model=AlmacenResponseModel, status_code=status.HTTP_201_CREATED
)
def registrar_almacen(
    payload: AlmacenCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Registra un nuevo almacén. Solo accesible por administradores."""
    return almacenServ.registrar_almacenServ(
        payload=payload, db=db, current_user=current_user
    )


@router.delete("/{almacen_id}", status_code=status.HTTP_200_OK)
def eliminar_almacen(
    almacen_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Elimina un almacén si no tiene dispositivos ni componentes asignados. Solo accesible por administradores."""
    return almacenServ.eliminar_almacenServ(
        almacen_id=almacen_id, db=db, current_user=current_user
    )
