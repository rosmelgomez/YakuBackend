from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.feedbackDto import (
    FeedbackCreate,
    FeedbackPreguntaCreate,
    FeedbackPreguntaResponse,
    FeedbackPreguntaUpdate,
    FeedbackResponse,
)
from src.main.service import feedbackServ

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def crear_feedback(
    data: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return feedbackServ.crear_feedbackServ(data=data, db=db, current_user=current_user)


@router.get("", response_model=list[FeedbackResponse])
def listar_feedback_propios(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    return feedbackServ.listar_feedback_propiosServ(db=db, current_user=current_user)


@router.get("/preguntas", response_model=list[FeedbackPreguntaResponse])
def listar_preguntas_feedback(
    incluir_inactivas: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return feedbackServ.listar_preguntas_feedbackServ(
        incluir_inactivas=incluir_inactivas, db=db, current_user=current_user
    )


@router.post(
    "/preguntas",
    response_model=FeedbackPreguntaResponse,
    status_code=status.HTTP_201_CREATED,
)
def crear_pregunta_feedback(
    data: FeedbackPreguntaCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return feedbackServ.crear_pregunta_feedbackServ(
        data=data, db=db, current_user=current_user
    )


@router.patch("/preguntas/{pregunta_id}", response_model=FeedbackPreguntaResponse)
def actualizar_pregunta_feedback(
    pregunta_id: int,
    data: FeedbackPreguntaUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return feedbackServ.actualizar_pregunta_feedbackServ(
        pregunta_id=pregunta_id, data=data, db=db, current_user=current_user
    )
