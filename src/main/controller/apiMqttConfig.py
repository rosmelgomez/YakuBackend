from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.mqttDto import (
    CredencialDispositivoGuardar,
    CredencialDispositivoResponse,
    MqttConfigResponse,
    MqttConfigUpdate,
)
from src.main.service import mqttConfigServ, mqttCredencialServ

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


@router.get("/credenciales", response_model=list[CredencialDispositivoResponse])
def listar_credenciales_dispositivos(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Dispositivos con el estado de su credencial MQTT (sin la clave)."""
    return mqttCredencialServ.listar_credencialesServ(db=db, current_user=current_user)


@router.put(
    "/credenciales/{id_dispositivo}", response_model=CredencialDispositivoResponse
)
def guardar_credencial_dispositivo(
    id_dispositivo: int,
    payload: CredencialDispositivoGuardar,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Registra o modifica la credencial MQTT de un dispositivo."""
    return mqttCredencialServ.guardar_credencialServ(
        id_dispositivo=id_dispositivo, payload=payload, db=db, current_user=current_user
    )


@router.delete(
    "/credenciales/{id_dispositivo}", status_code=status.HTTP_204_NO_CONTENT
)
def eliminar_credencial_dispositivo(
    id_dispositivo: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Elimina la credencial registrada (revóquela también en el broker)."""
    mqttCredencialServ.eliminar_credencialServ(
        id_dispositivo=id_dispositivo, db=db, current_user=current_user
    )
