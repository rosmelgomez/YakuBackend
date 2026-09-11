import logging
import os
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from src.main.core.mqttConfig import (
    MQTT_HOST,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_TLS_CA_CERT,
    MQTT_TLS_ENABLED,
    MQTT_TOPIC_CONTROL_AGUA,
    MQTT_TOPIC_RIEGO_DATOS,
    MQTT_USERNAME,
)
from src.main.core.yakuConfig import IS_PRODUCTION
from src.main.service import mqttServ

logger = logging.getLogger(__name__)

load_dotenv()

# ── Credenciales desde .env con HiveMQ Cloud ──────────────────────

_mqtt_client: mqtt.Client | None = None


def publish_mqtt_message(
    topic: str, payload: str, qos: int = 1, retain: bool = False
) -> None:
    """Publica un mensaje MQTT usando el cliente compartido de la aplicación."""
    global _mqtt_client

    if _mqtt_client is None:
        _mqtt_client = start_mqtt()

    if _mqtt_client is None:
        raise RuntimeError("No fue posible inicializar el cliente MQTT")

    deadline = time.time() + 5
    while not _mqtt_client.is_connected() and time.time() < deadline:
        time.sleep(0.1)

    if not _mqtt_client.is_connected():
        raise RuntimeError("Cliente MQTT no conectado; no se pudo publicar el comando")

    result = _mqtt_client.publish(topic, payload, qos=qos, retain=retain)
    result.wait_for_publish(timeout=5)

    if not result.is_published():
        raise RuntimeError(f"Timeout publicando en {topic}")

    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(f"Error publicando en {topic}: {result.rc}")


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    mqttServ.procesar_mensajeServ(client, userdata, msg)


def on_connect(
    client: mqtt.Client,
    userdata: Any,
    flags: dict[str, Any],
    rc: int,
    _properties: Any = None,
) -> None:
    """Callback al conectar al broker MQTT."""
    if rc == 0:
        logger.info(f"[OK] Conectado a MQTT broker {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_RIEGO_DATOS, qos=1)
        client.subscribe(MQTT_TOPIC_CONTROL_AGUA, qos=1)
        client.subscribe("yaku/dispositivo/+/config/req", qos=1)
        logger.info(
            f"   Suscrito a: {MQTT_TOPIC_RIEGO_DATOS}, {MQTT_TOPIC_CONTROL_AGUA}, yaku/dispositivo/+/config/req"
        )
    else:
        logger.info(f"[ERROR] Conexión MQTT falló con código: {rc}")


def start_mqtt() -> mqtt.Client | None:
    """Inicia el cliente MQTT con TLS y credenciales desde .env."""
    global _mqtt_client

    if IS_PRODUCTION and (
        not MQTT_TLS_ENABLED or not MQTT_USERNAME or not MQTT_PASSWORD
    ):
        raise RuntimeError("MQTT requiere TLS y credenciales en produccion")

    if _mqtt_client is not None:
        return _mqtt_client

    client = mqtt.Client()

    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    if MQTT_TLS_ENABLED:
        tls_kwargs = {}
        if MQTT_TLS_CA_CERT and os.path.isfile(MQTT_TLS_CA_CERT):
            tls_kwargs["ca_certs"] = MQTT_TLS_CA_CERT

        try:
            client.tls_set(**tls_kwargs)
            logger.info("[OK] TLS habilitado para MQTT")
        except Exception as e:
            if IS_PRODUCTION:
                raise RuntimeError("No fue posible configurar TLS para MQTT") from e
            logger.info(
                f"Advertencia: TLS setup falló ({e}); continuando sin validar certificado"
            )

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        _mqtt_client = client
        logger.info(f"[MQTT] Cliente iniciado (async)")
        return client
    except Exception as e:
        logger.info(f"[ERROR] Iniciando cliente MQTT: {e}")
        return None


def stop_mqtt() -> None:
    """Detiene el cliente MQTT."""
    global _mqtt_client

    if _mqtt_client is None:
        return

    client = _mqtt_client
    _mqtt_client = None

    try:
        client.disconnect()

        stopper = threading.Thread(target=client.loop_stop, daemon=True)
        stopper.start()
        stopper.join(timeout=3)
        if stopper.is_alive():
            logger.warning(
                "Timeout deteniendo el loop MQTT; se continuara con el apagado"
            )
            return

        logger.info("[OK] Cliente MQTT detenido")
    except Exception as e:
        logger.info(f"Advertencia al detener MQTT: {e}")
