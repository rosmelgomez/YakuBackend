"""Configuración administrable del broker MQTT (HU-08)."""

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.core.mqttConfig import (
    MQTT_HOST,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_TLS_ENABLED,
    MQTT_USERNAME,
)
from src.main.dtos.mqttDto import MqttConfigUpdate
from src.main.model.models import mqtt_config
from src.main.repositories import sessionRep as session_repository

logger = logging.getLogger(__name__)


def _obtener_o_crear_fila(db: Session) -> mqtt_config:
    fila = db.query(mqtt_config).order_by(mqtt_config.id.asc()).first()
    if fila is None:
        fila = mqtt_config(
            host=MQTT_HOST,
            port=MQTT_PORT,
            username=MQTT_USERNAME or None,
            password=MQTT_PASSWORD or None,
            usar_tls=MQTT_TLS_ENABLED,
        )
        session_repository.add(db, fila)
        session_repository.commit(db)
    return fila


def obtener_mqtt_configServ(db: Session = None, current_user=None) -> mqtt_config:
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para consultar esta configuración.",
        )
    return _obtener_o_crear_fila(db)


def obtener_configuracion_efectiva(db: Session) -> dict:
    """Usado en el arranque del backend para inicializar el cliente MQTT con
    la configuración persistida (si existe), o los valores de .env por defecto."""
    fila = _obtener_o_crear_fila(db)
    return {
        "host": fila.host,
        "port": fila.port,
        "username": fila.username or "",
        "password": fila.password or "",
        "tls_enabled": bool(fila.usar_tls),
    }


def actualizar_mqtt_configServ(
    payload: MqttConfigUpdate, db: Session = None, current_user=None
) -> mqtt_config:
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para modificar esta configuración.",
        )

    fila = _obtener_o_crear_fila(db)
    fila.host = payload.host
    fila.port = payload.port
    fila.username = payload.username
    if payload.password:
        fila.password = payload.password
    fila.usar_tls = payload.usar_tls
    fila.actualizado_por = current_user.id_usuario
    session_repository.add(db, fila)
    session_repository.commit(db)

    try:
        from src.main.tasks.mqttSubscriberTask import reiniciar_mqtt

        reiniciar_mqtt(
            {
                "host": fila.host,
                "port": fila.port,
                "username": fila.username or "",
                "password": fila.password or "",
                "tls_enabled": bool(fila.usar_tls),
            }
        )
    except Exception as exc:
        logger.exception("Error reiniciando el cliente MQTT tras actualizar configuración")
        raise HTTPException(
            status_code=500,
            detail=f"La configuración se guardó pero no fue posible reiniciar la conexión MQTT: {exc}",
        )

    return fila
