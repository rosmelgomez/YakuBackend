from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.horarioDto import (
    HorarioRiegoCreate,
    HorarioRiegoResponse,
    HorarioRiegoUpdate,
)
from src.main.service import horarioServ

router = APIRouter(prefix="/horarios-riego", tags=["Horarios de Riego"])


@router.get("", response_model=List[HorarioRiegoResponse])
def listar_horarios(
    id_asignacion: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Lista los horarios fijos de riego del usuario (HU-17)."""
    return horarioServ.listar_horariosServ(
        id_asignacion=id_asignacion, db=db, current_user=current_user
    )


@router.post("", response_model=HorarioRiegoResponse, status_code=status.HTTP_201_CREATED)
def crear_horario(
    payload: HorarioRiegoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Crea un horario fijo de riego (hora, duración y días de la semana)."""
    return horarioServ.crear_horarioServ(payload=payload, db=db, current_user=current_user)


@router.put("/{id_horario}", response_model=HorarioRiegoResponse)
def actualizar_horario(
    id_horario: int,
    payload: HorarioRiegoUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Actualiza un horario fijo de riego existente."""
    return horarioServ.actualizar_horarioServ(
        id_horario=id_horario, payload=payload, db=db, current_user=current_user
    )


@router.delete("/{id_horario}")
def eliminar_horario(
    id_horario: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Elimina un horario fijo de riego."""
    return horarioServ.eliminar_horarioServ(
        id_horario=id_horario, db=db, current_user=current_user
    )
