import os
import json
import logging
from pywebpush import webpush, WebPushException
from dotenv import load_dotenv
from src.config import VAPIDConfig

load_dotenv()
logger = logging.getLogger(__name__)

def enviar_webpush(subscription_info: dict, title: str, message: str) -> bool | str:
    """Envía una notificación Web Push cifrada usando pywebpush."""
    vapid_private_key = VAPIDConfig.PRIVATE_KEY
    vapid_public_key = VAPIDConfig.PUBLIC_KEY
    vapid_claims_email = VAPIDConfig.CLAIMS_EMAIL

    if not vapid_private_key or not vapid_public_key:
        logger.warning("VAPID no configurado; se omite Web Push")
        return False

    try:
        payload = {
            "title": title,
            "message": message
        }
        
        # Enviar notificación push
        response = webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=vapid_private_key,
            vapid_claims={"sub": f"mailto:{vapid_claims_email}"}
        )
        
        logger.debug("Notificación Web Push enviada")
        return True
    except WebPushException as ex:
        logger.info(f"[WEBPUSH] Error enviando Web Push: {ex}")
        # 410 o 404 significa que la suscripción caducó o el usuario bloqueó las notificaciones
        if ex.response is not None and ex.response.status_code in [404, 410]:
            logger.info("[WEBPUSH] Suscripción expirada o bloqueada en el dispositivo final.")
            return "EXPIRED"
        return False
    except Exception as e:
        logger.info(f"[WEBPUSH] Error inesperado en envío Web Push: {e}")
        return False
