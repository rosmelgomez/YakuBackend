from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.config import VAPIDConfig
from pydantic import BaseModel
from ..dependencies import get_db
from ...core.bff_auth import get_current_user_or_bff
from ...db.models import suscripciones_push

router = APIRouter(tags=["Web Push"])

class KeysModel(BaseModel):
    p256dh: str
    auth: str

class SubscribeModel(BaseModel):
    endpoint: str
    keys: KeysModel

@router.get("/webpush/public-key")
def get_public_key():
    pub_key = VAPIDConfig.PUBLIC_KEY
    if not pub_key:
        raise HTTPException(status_code=500, detail="VAPID keys no están configuradas en el backend.")
    return {"publicKey": pub_key}

@router.post("/webpush/subscribe")
def subscribe_user(
    data: SubscribeModel,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_or_bff)
):
    try:
        # Verificar si la suscripción ya existe
        existing = db.query(suscripciones_push).filter(suscripciones_push.endpoint == data.endpoint).first()
        if existing:
            existing.id_usuario = current_user.id_usuario
            existing.key_p256dh = data.keys.p256dh
            existing.key_auth = data.keys.auth
            db.commit()
            return {"success": True, "message": "Suscripción actualizada correctamente."}
        
        # Registrar nueva suscripción
        new_sub = suscripciones_push(
            id_usuario=current_user.id_usuario,
            endpoint=data.endpoint,
            key_p256dh=data.keys.p256dh,
            key_auth=data.keys.auth
        )
        db.add(new_sub)
        db.commit()
        return {"success": True, "message": "Suscripción registrada con éxito."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error interno del servidor")
