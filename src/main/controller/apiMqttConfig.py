from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.mqttDto import MqttConfigResponse, MqttConfigUpdate
from src.main.service import mqttConfigServ

router = APIRouter(prefix="/admin/mqtt-config", tags=["Configuración MQTT"])


@router.get("", response_model=MqttConfigResponse)
def obtener_mqtt_config(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Obtiene la configuración actual del broker MQTT (HU-08). Solo administradores."""
    return mqttConfigServ.obtener_mqtt_configServ(db=db, current_user=current_user)


@router.put("", response_model=MqttConfigResponse)
def actualizar_mqtt_config(
    payload: MqttConfigUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Actualiza la configuración del broker MQTT y reinicia la conexión en caliente."""
    return mqttConfigServ.actualizar_mqtt_configServ(
        payload=payload, db=db, current_user=current_user
    )
