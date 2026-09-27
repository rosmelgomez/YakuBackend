import logging
import os
import threading
import time
from datetime import datetime, timezone
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
from src.main.core.yakuConfig import IOT_TASKS_ENABLED, IS_PRODUCTION
from src.main.service import mqttServ
from src.main.service.networkLogServ import registrar_evento_red

logger = logging.getLogger(__name__)

load_dotenv()

# ── Credenciales desde .env con HiveMQ Cloud (valores por defecto,
#    sobreescribibles en caliente vía HU-08 / mqttConfigServ) ──────

_mqtt_client: mqtt.Client | None = None
_deliberate_disconnect = False

_current_config: dict[str, Any] = {
    "host": MQTT_HOST,
    "port": MQTT_PORT,
    "username": MQTT_USERNAME,
    "password": MQTT_PASSWORD,
    "tls_enabled": MQTT_TLS_ENABLED,
}

# ── Estado real de la conexion, para el panel de administracion ──────────
# Se actualiza en los callbacks de paho (hilo de red) y se lee desde la API.
_estado_lock = threading.Lock()
_estado: dict[str, Any] = {
    "estado": "desconectado",
    "codigo": None,
    "mensaje": "El cliente MQTT aún no se ha iniciado.",
    "desde": None,
}

# Codigos CONNACK de MQTT 3.1.1 con los que el broker rechaza una conexion.
_MOTIVOS_RECHAZO = {
    1: "El broker rechazó la versión del protocolo MQTT.",
    2: "El broker rechazó el identificador de cliente (client_id).",
    3: "El broker no está disponible en este momento.",
    4: "Usuario o contraseña incorrectos.",
    5: "No autorizado: el usuario no existe en el broker, la contraseña es "
    "incorrecta o no tiene permiso para publicar y suscribirse.",
}


def _codigo(rc: Any) -> int:
    return int(getattr(rc, "value", rc))


def _actualizar_estado(estado: str, mensaje: str, codigo: int | None = None) -> None:
    with _estado_lock:
        _estado.update(
            estado=estado,
            codigo=codigo,
            mensaje=mensaje,
            desde=datetime.now(timezone.utc).replace(tzinfo=None),
        )


def obtener_estado_mqtt() -> dict[str, Any]:
    """Estado actual de la conexion del backend con el broker (sin la clave)."""
    with _estado_lock:
        estado = dict(_estado)
    estado.update(
        host=_current_config.get("host"),
        port=_current_config.get("port"),
        username=_current_config.get("username") or None,
        tls=bool(_current_config.get("tls_enabled")),
    )
    return estado


def _es_cliente_actual(client: mqtt.Client) -> bool:
    # Al reiniciar, el cliente anterior puede seguir disparando callbacks
    # (desconexion) mientras el nuevo conecta: esos eventos no deben pisar
    # el estado del cliente vigente.
    return client is _mqtt_client


def publish_mqtt_message(
    topic: str, payload: str, qos: int = 1, retain: bool = False
) -> None:
    """Publica un mensaje MQTT usando el cliente compartido de la aplicación."""
    global _mqtt_client

    if _mqtt_client is None:
        _mqtt_client = start_mqtt()

    if _mqtt_client is None:
        raise RuntimeError("No fue posible inicializar el cliente MQTT")

    # Llamado desde un callback (on_message -> telemetria -> ML -> riego) se
    # ejecuta en el hilo de red de paho: ese hilo es el unico que escribe en
    # el socket y lee el PUBACK, asi que esperar aqui siempre agotaba el
    # timeout y lanzaba error, aunque el mensaje SI salia al volver del
    # callback (p.ej. el ON llegaba al equipo pero el riego se revertia en BD).
    # En ese hilo solo se encola; paho lo envia al terminar el callback.
    if threading.current_thread() is getattr(_mqtt_client, "_thread", None):
        if not _mqtt_client.is_connected():
            raise RuntimeError("Cliente MQTT no conectado; no se pudo publicar el comando")
        result = _mqtt_client.publish(topic, payload, qos=qos, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            error_msg = f"Error publicando en {topic}: {result.rc}"
            registrar_evento_red("mqtt_publicacion_fallida", error_msg)
            raise RuntimeError(error_msg)
        return

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
        error_msg = f"Error publicando en {topic}: {result.rc}"
        registrar_evento_red("mqtt_publicacion_fallida", error_msg)
        raise RuntimeError(error_msg)


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
    rc = _codigo(rc)
    if _es_cliente_actual(client):
        if rc == 0:
            _actualizar_estado("conectado", "Conectado al broker.")
        else:
            _actualizar_estado(
                "error",
                _MOTIVOS_RECHAZO.get(rc, f"El broker rechazó la conexión (código {rc})."),
                rc,
            )
    if rc == 0:
        logger.info(
            f"[OK] Conectado a MQTT broker {_current_config['host']}:{_current_config['port']}"
        )
        if not IOT_TASKS_ENABLED:
            logger.info("[MQTT] IOT_TASKS_ENABLED=false: sin suscripciones (solo publicacion).")
            return
        client.subscribe(MQTT_TOPIC_RIEGO_DATOS, qos=1)
        client.subscribe(MQTT_TOPIC_CONTROL_AGUA, qos=1)
        client.subscribe("yaku/dispositivo/+/config/req", qos=1)
        logger.info(
            f"   Suscrito a: {MQTT_TOPIC_RIEGO_DATOS}, {MQTT_TOPIC_CONTROL_AGUA}, yaku/dispositivo/+/config/req"
        )
    else:
        logger.info(f"[ERROR] Conexión MQTT falló con código: {rc}")
        registrar_evento_red(
            "mqtt_conexion_fallida",
            f"Falló la conexión al broker {_current_config['host']}:{_current_config['port']} (código {rc}).",
        )


def on_disconnect(
    client: mqtt.Client,
    userdata: Any,
    rc: int,
    _properties: Any = None,
) -> None:
    """Callback de desconexión. Solo registra como incidente de red las
    desconexiones inesperadas (rc != 0); una desconexión deliberada (por
    `stop_mqtt`/`reiniciar_mqtt`) no se reporta como error."""
    rc = _codigo(rc)
    if rc != 0 and not _deliberate_disconnect and _es_cliente_actual(client):
        # Si fue un rechazo de credenciales, on_connect ya dejo el motivo.
        with _estado_lock:
            ya_en_error = _estado["estado"] == "error"
        if not ya_en_error:
            _actualizar_estado(
                "desconectado",
                f"Se perdió la conexión con el broker ({mqtt.error_string(rc)}). "
                "Reintentando automáticamente.",
                rc,
            )
    if rc != 0 and not _deliberate_disconnect:
        logger.warning(f"[MQTT] Desconexión inesperada del broker (código {rc})")
        registrar_evento_red(
            "mqtt_desconexion_inesperada",
            f"El cliente MQTT se desconectó inesperadamente del broker (código {rc}).",
        )


def on_connect_fail(client: mqtt.Client, userdata: Any) -> None:
    """No se pudo abrir la conexion (red, DNS, puerto o TLS): el broker ni
    siquiera llego a responder. paho reintenta solo."""
    if not _es_cliente_actual(client):
        return
    host, port = _current_config["host"], _current_config["port"]
    _actualizar_estado(
        "error",
        f"No se pudo abrir la conexión con {host}:{port}. Revise el host, el puerto, "
        "el TLS y la salida a internet del servidor.",
    )
    registrar_evento_red(
        "mqtt_conexion_fallida",
        f"No se pudo abrir la conexión con el broker {host}:{port} (red, DNS, puerto o TLS).",
    )


def start_mqtt(overrides: dict[str, Any] | None = None) -> mqtt.Client | None:
    """Inicia el cliente MQTT. Usa `overrides` (host/port/username/password/tls_enabled)
    si se proveen (config administrable vía HU-08); de lo contrario usa la última
    configuración conocida (por defecto, la de .env)."""
    global _mqtt_client, _current_config

    if overrides:
        _current_config = {**_current_config, **overrides}

    host = _current_config["host"]
    port = _current_config["port"]
    username = _current_config["username"]
    password = _current_config["password"]
    tls_enabled = _current_config["tls_enabled"]

    if IS_PRODUCTION and (not tls_enabled or not username or not password):
        _actualizar_estado(
            "error", "En producción MQTT requiere TLS, usuario y contraseña configurados."
        )
        raise RuntimeError("MQTT requiere TLS y credenciales en produccion")

    if _mqtt_client is not None:
        return _mqtt_client

    client = mqtt.Client()

    if username and password:
        client.username_pw_set(username, password)

    if tls_enabled:
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
    client.on_connect_fail = on_connect_fail
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    global _deliberate_disconnect
    _deliberate_disconnect = False

    try:
        # Se marca como vigente ANTES de conectar: el callback de conexion puede
        # llegar desde el hilo de red antes de que esta funcion termine.
        _mqtt_client = client
        _actualizar_estado("conectando", f"Conectando con {host}:{port}...")
        client.connect_async(host, port, keepalive=60)
        client.loop_start()
        logger.info(f"[MQTT] Cliente iniciado (async)")
        return client
    except Exception as e:
        _mqtt_client = None
        _actualizar_estado("error", f"No se pudo iniciar el cliente MQTT: {e}")
        logger.info(f"[ERROR] Iniciando cliente MQTT: {e}")
        registrar_evento_red(
            "mqtt_conexion_fallida", f"Excepción al iniciar el cliente MQTT: {e}"
        )
        return None


def reiniciar_mqtt(overrides: dict[str, Any]) -> mqtt.Client | None:
    """Detiene el cliente MQTT actual y lo reinicia con la nueva configuración
    (usado al guardar cambios desde el panel de administración, HU-08)."""
    stop_mqtt()
    return start_mqtt(overrides=overrides)


def stop_mqtt() -> None:
    """Detiene el cliente MQTT."""
    global _mqtt_client, _deliberate_disconnect

    if _mqtt_client is None:
        return

    client = _mqtt_client
    _mqtt_client = None
    _deliberate_disconnect = True
    _actualizar_estado("desconectado", "Cliente MQTT detenido.")

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
