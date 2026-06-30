from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...core.bff_auth import get_current_user_or_bff
from ...db.models import cultivos, feedback_agricultores, feedback_preguntas, feedback_respuestas, logs_sistema
from ...schemas.feedback import (
    FeedbackCreate,
    FeedbackPreguntaCreate,
    FeedbackPreguntaResponse,
    FeedbackPreguntaUpdate,
    FeedbackResponse,
    FeedbackRespuestaResponse,
)
from ..dependencies import get_db


router = APIRouter(prefix="/feedback", tags=["Feedback"])

DEFAULT_FEEDBACK_QUESTIONS = [
    "Te parecio facil usar y entender el sistema Yaku?",
    "Fueron claras las recomendaciones y alertas del sistema?",
    "Consideras utiles o adecuadas las recomendaciones de riego?",
    "La interaccion con el sistema se realizo sin dificultades?",
    "Estas satisfecho con la experiencia general del sistema?",
]


def _require_admin(current_user) -> None:
    if current_user.id_rol != 1:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permisos de administrador requeridos")


def _require_farmer(current_user) -> None:
    if current_user.id_rol != 2:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo agricultores pueden registrar feedback")


def _ensure_default_questions(db: Session) -> None:
    if db.query(feedback_preguntas).count() > 0:
        return
    for index, pregunta in enumerate(DEFAULT_FEEDBACK_QUESTIONS, start=1):
        db.add(feedback_preguntas(pregunta=pregunta, orden=index, activo=True))
    db.commit()


def _question_response(item: feedback_preguntas) -> FeedbackPreguntaResponse:
    return FeedbackPreguntaResponse(
        id=item.id,
        pregunta=item.pregunta,
        descripcion=item.descripcion,
        orden=item.orden,
        activo=item.activo,
        fecha_registro=item.fecha_registro,
        actualizado_en=item.actualizado_en,
    )


def _feedback_response(item: feedback_agricultores) -> FeedbackResponse:
    return FeedbackResponse(
        id=item.id,
        id_usuario=item.id_usuario,
        id_cultivo=item.id_cultivo,
        cultivo_nombre=item.cultivo.nombre_planta if item.cultivo else None,
        modulo=item.modulo,
        tipo=item.tipo,
        calificacion=item.calificacion,
        mensaje=item.mensaje,
        estado=item.estado,
        fecha=item.fecha,
        respuestas=[
            FeedbackRespuestaResponse(
                id=respuesta.id,
                id_pregunta=respuesta.id_pregunta,
                pregunta=respuesta.pregunta.pregunta if respuesta.pregunta else "Pregunta no disponible",
                calificacion=respuesta.calificacion,
            )
            for respuesta in sorted(item.respuestas, key=lambda respuesta: respuesta.pregunta.orden if respuesta.pregunta else 0)
        ],
    )


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def crear_feedback(
    data: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    _require_farmer(current_user)

    cultivo = None
    if data.id_cultivo is not None:
        cultivo = db.query(cultivos).filter(
            cultivos.id_cultivo == data.id_cultivo,
            cultivos.id_usuario == current_user.id_usuario,
            cultivos.estado == "activo",
        ).first()
        if not cultivo:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cultivo no encontrado")

    question_ids = [respuesta.id_pregunta for respuesta in data.respuestas]
    if len(question_ids) != len(set(question_ids)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No se permiten respuestas duplicadas")

    preguntas = db.query(feedback_preguntas).filter(
        feedback_preguntas.id.in_(question_ids),
        feedback_preguntas.activo.is_(True),
    ).all()
    if len(preguntas) != len(question_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Una o mas preguntas no estan activas")

    promedio = round(sum(respuesta.calificacion for respuesta in data.respuestas) / len(data.respuestas))
    comentario = data.comentario or "Sin comentario adicional"

    item = feedback_agricultores(
        id_usuario=current_user.id_usuario,
        id_cultivo=cultivo.id_cultivo if cultivo else None,
        modulo="Encuesta del sistema",
        tipo="encuesta",
        calificacion=promedio,
        mensaje=comentario,
    )
    db.add(item)
    db.flush()

    for respuesta in data.respuestas:
        db.add(feedback_respuestas(
            id_feedback=item.id,
            id_pregunta=respuesta.id_pregunta,
            calificacion=respuesta.calificacion,
        ))

    db.add(logs_sistema(
        id_usuario=current_user.id_usuario,
        accion="crear_feedback",
        modulo="feedback",
        descripcion=f"Encuesta de feedback registrada con promedio {promedio}/5",
    ))
    db.commit()
    db.refresh(item)
    return _feedback_response(item)


@router.get("", response_model=list[FeedbackResponse])
def listar_feedback_propios(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    items = db.query(feedback_agricultores).filter(
        feedback_agricultores.id_usuario == current_user.id_usuario,
    ).order_by(feedback_agricultores.fecha.desc()).limit(20).all()
    return [_feedback_response(item) for item in items]


@router.get("/preguntas", response_model=list[FeedbackPreguntaResponse])
def listar_preguntas_feedback(
    incluir_inactivas: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    _ensure_default_questions(db)
    query = db.query(feedback_preguntas)
    if not incluir_inactivas or current_user.id_rol != 1:
        query = query.filter(feedback_preguntas.activo.is_(True))
    return [_question_response(item) for item in query.order_by(feedback_preguntas.orden.asc(), feedback_preguntas.id.asc()).all()]


@router.post("/preguntas", response_model=FeedbackPreguntaResponse, status_code=status.HTTP_201_CREATED)
def crear_pregunta_feedback(
    data: FeedbackPreguntaCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    _require_admin(current_user)
    item = feedback_preguntas(
        pregunta=data.pregunta,
        descripcion=data.descripcion,
        orden=data.orden,
        activo=data.activo,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _question_response(item)


@router.patch("/preguntas/{pregunta_id}", response_model=FeedbackPreguntaResponse)
def actualizar_pregunta_feedback(
    pregunta_id: int,
    data: FeedbackPreguntaUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    _require_admin(current_user)
    item = db.query(feedback_preguntas).filter(feedback_preguntas.id == pregunta_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pregunta no encontrada")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _question_response(item)
