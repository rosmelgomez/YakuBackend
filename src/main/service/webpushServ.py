from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.main.core.notificationConfig import VAPIDConfig
from src.main.dtos.webpushDto import SubscribeModel
from src.main.model.models import suscripciones_push
from src.main.repositories import sessionRep as session_repository
from src.main.repositories import webpushRep as data_repository


def get_public_keyServ():
    pub_key = VAPIDConfig.PUBLIC_KEY
    if not pub_key:
        raise HTTPException(
            status_code=500, detail="VAPID keys no están configuradas en el backend."
        )
    return {"publicKey": pub_key}


def get_push_statusServ(db: Session = None, current_user=None):
    subscription_count = data_repository.queryGetPushStatusSubscriptionCount(
        db, current_user
    )
    return {
        "registered": subscription_count > 0,
        "subscriptionCount": subscription_count,
    }


def subscribe_userServ(data: SubscribeModel, db: Session = None, current_user=None):
    try:
        # Verificar si la suscripción ya existe
        existing = data_repository.querySubscribeUserExisting(db, data)
        if existing:
            existing.id_usuario = current_user.id_usuario
            existing.key_p256dh = data.keys.p256dh
            existing.key_auth = data.keys.auth
            session_repository.commit(db)
            return {
                "success": True,
                "message": "Suscripción actualizada correctamente.",
            }

        # Registrar nueva suscripción
        new_sub = suscripciones_push(
            id_usuario=current_user.id_usuario,
            endpoint=data.endpoint,
            key_p256dh=data.keys.p256dh,
            key_auth=data.keys.auth,
        )
        session_repository.add(db, new_sub)
        session_repository.commit(db)
        return {"success": True, "message": "Suscripción registrada con éxito."}
    except Exception as e:
        session_repository.rollback(db)
        raise HTTPException(status_code=500, detail="Error interno del servidor")
