from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.dtos.feedbackDto import (
    FeedbackCreate,
    FeedbackPreguntaCreate,
    FeedbackPreguntaResponse,
    FeedbackPreguntaUpdate,
    FeedbackResponse,
    FeedbackRespuestaResponse,
)
from src.main.model.models import (
    feedback_agricultores,
    feedback_preguntas,
    feedback_respuestas,
    logs_sistema,
)
from src.main.repositories import feedbackRep as data_repository
from src.main.repositories import sessionRep as session_repository

DEFAULT_FEEDBACK_QUESTIONS = [
    "Te parecio facil usar y entender el sistema Yaku?",
    "Fueron claras las recomendaciones y alertas del sistema?",
    "Consideras utiles o adecuadas las recomendaciones de riego?",
    "La interaccion con el sistema se realizo sin dificultades?",
    "Estas satisfecho con la experiencia general del sistema?",
]


def _require_admin(current_user) -> None:
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos de administrador requeridos",
        )


def _require_farmer(current_user) -> None:
    if current_user.id_rol != 2:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo agricultores pueden registrar feedback",
        )


def _ensure_default_questions(db: Session) -> None:
    if data_repository.queryEnsureDefaultQuestionsFeedbackPreguntas(db) > 0:
        return
    for index, pregunta in enumerate(DEFAULT_FEEDBACK_QUESTIONS, start=1):
        session_repository.add(
            db, feedback_preguntas(pregunta=pregunta, orden=index, activo=True)
        )
    session_repository.commit(db)


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
                pregunta=respuesta.pregunta.pregunta
                if respuesta.pregunta
                else "Pregunta no disponible",
                calificacion=respuesta.calificacion,
            )
            for respuesta in sorted(
                item.respuestas,
                key=lambda respuesta: (
                    respuesta.pregunta.orden if respuesta.pregunta else 0
                ),
            )
        ],
    )


def crear_feedbackServ(data: FeedbackCreate, db: Session = None, current_user=None):
    _require_farmer(current_user)

    cultivo = None
    if data.id_cultivo is not None:
        cultivo = data_repository.queryCrearFeedbackCultivo(db, data, current_user)
        if not cultivo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Cultivo no encontrado"
            )

    question_ids = [respuesta.id_pregunta for respuesta in data.respuestas]
    if len(question_ids) != len(set(question_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se permiten respuestas duplicadas",
        )

    preguntas = data_repository.queryCrearFeedbackPreguntas(db, question_ids)
    if len(preguntas) != len(question_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Una o mas preguntas no estan activas",
        )

    promedio = round(
        sum(respuesta.calificacion for respuesta in data.respuestas)
        / len(data.respuestas)
    )
    comentario = data.comentario or "Sin comentario adicional"

    item = feedback_agricultores(
        id_usuario=current_user.id_usuario,
        id_cultivo=cultivo.id_cultivo if cultivo else None,
        modulo="Encuesta del sistema",
        tipo="encuesta",
        calificacion=promedio,
        mensaje=comentario,
    )
    session_repository.add(db, item)
    session_repository.flush(db)

    for respuesta in data.respuestas:
        session_repository.add(
            db,
            feedback_respuestas(
                id_feedback=item.id,
                id_pregunta=respuesta.id_pregunta,
                calificacion=respuesta.calificacion,
            ),
        )

    session_repository.add(
        db,
        logs_sistema(
            id_usuario=current_user.id_usuario,
            accion="crear_feedback",
            modulo="feedback",
            descripcion=f"Encuesta de feedback registrada con promedio {promedio}/5",
        ),
    )
    session_repository.commit(db)
    session_repository.refresh(db, item)
    return _feedback_response(item)


def listar_feedback_propiosServ(db: Session = None, current_user=None):
    items = data_repository.queryListarFeedbackPropiosItems(db, current_user)
    return [_feedback_response(item) for item in items]


def listar_preguntas_feedbackServ(
    incluir_inactivas: bool = False, db: Session = None, current_user=None
):
    _ensure_default_questions(db)
    query = data_repository.queryListarPreguntasFeedbackQuery(db)
    if not incluir_inactivas or current_user.id_rol != 1:
        query = data_repository.queryListarPreguntasFeedbackQuery2(query)
    return [
        _question_response(item)
        for item in data_repository.queryListarPreguntasFeedbackFeedbackPreguntas(query)
    ]


def crear_pregunta_feedbackServ(
    data: FeedbackPreguntaCreate, db: Session = None, current_user=None
):
    _require_admin(current_user)
    item = feedback_preguntas(
        pregunta=data.pregunta,
        descripcion=data.descripcion,
        orden=data.orden,
        activo=data.activo,
    )
    session_repository.add(db, item)
    session_repository.commit(db)
    session_repository.refresh(db, item)
    return _question_response(item)


def actualizar_pregunta_feedbackServ(
    pregunta_id: int,
    data: FeedbackPreguntaUpdate,
    db: Session = None,
    current_user=None,
):
    _require_admin(current_user)
    item = data_repository.queryActualizarPreguntaFeedbackItem(db, pregunta_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pregunta no encontrada"
        )

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    session_repository.commit(db)
    session_repository.refresh(db, item)
    return _question_response(item)
