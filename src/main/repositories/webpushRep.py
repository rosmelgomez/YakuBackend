from sqlalchemy.orm import Session

from src.main.model.models import suscripciones_push


def queryGetPushStatusSubscriptionCount(db: Session, current_user):
    return (
        db.query(suscripciones_push)
        .filter(suscripciones_push.id_usuario == current_user.id_usuario)
        .count()
    )


def querySubscribeUserExisting(db: Session, data):
    return (
        db.query(suscripciones_push)
        .filter(suscripciones_push.endpoint == data.endpoint)
        .first()
    )
