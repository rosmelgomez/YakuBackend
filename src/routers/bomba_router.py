from fastapi import APIRouter, Depends, HTTPException, status

from ..tasks.mqtt_subscriber import publish_mqtt_message
from .auth import get_current_user

router = APIRouter(prefix="/bomba", tags=["Bomba"])
MQTT_TOPIC_CONTROL = "yaku/riego/control_agua"


@router.post("/activar")
def activar_bomba(_current_user=Depends(get_current_user)):
    try:
        publish_mqtt_message(MQTT_TOPIC_CONTROL, "ON", qos=1, retain=True)
        return {"status": "ok", "accion": "activar", "topic": MQTT_TOPIC_CONTROL}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/desactivar")
def desactivar_bomba(_current_user=Depends(get_current_user)):
    try:
        publish_mqtt_message(MQTT_TOPIC_CONTROL, "OFF", qos=1, retain=True)
        return {"status": "ok", "accion": "desactivar", "topic": MQTT_TOPIC_CONTROL}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc