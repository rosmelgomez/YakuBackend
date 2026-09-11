from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.plantaDto import (
    PlantaCreate,
    PlantaResponseModel,
    UmbralPlantaSchema,
)
from src.main.service import plantaServ

router = APIRouter(prefix="/plantas", tags=["Catálogo de Plantas"])


@router.get("", response_model=List[PlantaResponseModel])
def listar_plantas(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """Obtiene el catálogo completo de plantas."""
    return plantaServ.listar_plantasServ(db=db, current_user=current_user)


@router.post(
    "", response_model=PlantaResponseModel, status_code=status.HTTP_201_CREATED
)
def registrar_planta(
    payload: PlantaCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Registra una nueva especie de planta en el catálogo. Solo administradores."""
    return plantaServ.registrar_plantaServ(
        payload=payload, db=db, current_user=current_user
    )


@router.put("/{planta_id}/umbrales", response_model=List[UmbralPlantaSchema])
def actualizar_umbrales_planta(
    planta_id: int,
    payload: List[UmbralPlantaSchema],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Agrega o modifica los rangos recomendados de una planta."""
    return plantaServ.actualizar_umbrales_plantaServ(
        planta_id=planta_id, payload=payload, db=db, current_user=current_user
    )
