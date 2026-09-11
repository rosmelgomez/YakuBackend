from sqlalchemy.orm import Session

from src.main.model.models import cultivos, feedback_agricultores, feedback_preguntas


def queryEnsureDefaultQuestionsFeedbackPreguntas(db: Session):
    return db.query(feedback_preguntas).count()


def queryCrearFeedbackCultivo(db: Session, data, current_user):
    return (
        db.query(cultivos)
        .filter(
            cultivos.id_cultivo == data.id_cultivo,
            cultivos.id_usuario == current_user.id_usuario,
            cultivos.estado == "activo",
        )
        .first()
    )


def queryCrearFeedbackPreguntas(db: Session, question_ids):
    return (
        db.query(feedback_preguntas)
        .filter(
            feedback_preguntas.id.in_(question_ids), feedback_preguntas.activo.is_(True)
        )
        .all()
    )


def queryListarFeedbackPropiosItems(db: Session, current_user):
    return (
        db.query(feedback_agricultores)
        .filter(feedback_agricultores.id_usuario == current_user.id_usuario)
        .order_by(feedback_agricultores.fecha.desc())
        .limit(20)
        .all()
    )


def queryListarPreguntasFeedbackQuery(db: Session):
    return db.query(feedback_preguntas)


def queryListarPreguntasFeedbackQuery2(query):
    return query.filter(feedback_preguntas.activo.is_(True))


def queryListarPreguntasFeedbackFeedbackPreguntas(query):
    return query.order_by(
        feedback_preguntas.orden.asc(), feedback_preguntas.id.asc()
    ).all()


def queryActualizarPreguntaFeedbackItem(db: Session, pregunta_id):
    return (
        db.query(feedback_preguntas)
        .filter(feedback_preguntas.id == pregunta_id)
        .first()
    )
