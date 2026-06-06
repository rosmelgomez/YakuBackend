import json
import os
from typing import Any

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from src.Model import crud
from src.Model.conexion import SessionLocal
from src.Model.schemas import TelemetriaTanqueModel, RiegoDatosModel, PrediccionRiegoModel
from src.Router.ml_router import obtener_prediccion_riego

load_dotenv()

# ── Credenciales desde .env con HiveMQ Cloud ──────────────────────
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC_RIEGO_DATOS = os.getenv("MQTT_TOPIC_RIEGO_DATOS", "yaku/riego/datos")
MQTT_TOPIC_CONTROL_CMD = os.getenv("MQTT_TOPIC_CONTROL_CMD", "yaku/riego/comando")
MQTT_TOPIC_CONTROL_AGUA = os.getenv("MQTT_TOPIC_CONTROL_AGUA", "yaku/tanque/datos")
MQTT_TLS_ENABLED = os.getenv("MQTT_TLS_ENABLED", "true").lower() in {"1", "true", "yes"}
MQTT_TLS_CA_CERT = os.getenv("MQTT_TLS_CA_CERT", "")

_mqtt_client: mqtt.Client | None = None


def publish_mqtt_message(topic: str, payload: str, qos: int = 1, retain: bool = False) -> None:
    """Publica un mensaje MQTT usando el cliente compartido de la aplicación."""
    global _mqtt_client

    if _mqtt_client is None:
        _mqtt_client = start_mqtt()

    if _mqtt_client is None:
        raise RuntimeError("No fue posible inicializar el cliente MQTT")

    result = _mqtt_client.publish(topic, payload, qos=qos, retain=retain)
    result.wait_for_publish()

    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(f"Error publicando en {topic}: {result.rc}")


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    """Procesa mensajes MQTT y guarda en PostgreSQL según el tópico."""
    db = SessionLocal()
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        print(f"[MQTT] Recibido en {msg.topic}: {payload}")

        if msg.topic == MQTT_TOPIC_RIEGO_DATOS:
            # Resolver el dispositivo primero antes de guardar para verificar si está activo
            device_id = payload.get("device_id")
            dispositivo = None
            if device_id:
                from src.Model.model import dispositivos
                dispositivo = db.query(dispositivos).filter(
                    (dispositivos.client_id_mqtt == device_id) | (dispositivos.nombre == device_id)
                ).first()

            if dispositivo and not dispositivo.funcionamiento_activo:
                print(f"[PAUSED] Dispositivo '{device_id}' desactivado por el usuario. Descartando telemetría de sensores.")
                return

            data = RiegoDatosModel(**payload)
            id_dispositivo = dispositivo.id_dispositivo if dispositivo else None
            crud.crear_datos_riego(db, data, id_dispositivo=id_dispositivo)
            print("[OK] Datos de riego guardados en PostgreSQL")

            # Enviar los valores al modelo ML para obtener decisión de riego
            try:
                id_usuario = dispositivo.id_usuario if dispositivo else None
                if not id_usuario:
                    from src.Model.model import usuarios
                    primer_usuario = db.query(usuarios).order_by(usuarios.id_usuario.asc()).first()
                    if primer_usuario:
                        id_usuario = primer_usuario.id_usuario

                pred_input = PrediccionRiegoModel(
                    humedad_suelo=float(data.humedad_suelo.valor) if data.humedad_suelo.valor is not None else 0.0,
                    humedad_ambiente=float(data.humedad_ambiente.valor) if data.humedad_ambiente.valor is not None else 0.0,
                    temperatura_ambiente=float(data.temperatura_ambiente.temperatura) if data.temperatura_ambiente.temperatura is not None else 0.0,
                    temperatura_suelo=float(data.temperatura_suelo.temperatura) if data.temperatura_suelo.temperatura is not None else 0.0,
                )
                id_dispositivo = dispositivo.id_dispositivo if dispositivo else None
                resultado = obtener_prediccion_riego(
                    pred_input,
                    db,
                    id_usuario=id_usuario,
                    id_dispositivo=id_dispositivo
                )
                print(f"[ML] Resultado ML: {resultado}")

                # Publicar comando de control al ESP32 (ON/OFF)
                try:
                    comando = "ON" if int(resultado.get("riego", 0)) == 1 else "OFF"
                    client.publish(MQTT_TOPIC_CONTROL_CMD, comando, qos=1, retain=True)
                    print(f"[MQTT] Publicado comando '{comando}' en {MQTT_TOPIC_CONTROL_CMD}")
                except Exception as pub_exc:
                    print(f"[ERROR] Publicando comando MQTT: {pub_exc}")

            except Exception as ml_exc:
                print(f"[ERROR] Al invocar ML para predicción: {ml_exc}")

        elif msg.topic == MQTT_TOPIC_CONTROL_AGUA:
            data = TelemetriaTanqueModel(**payload)

            # Verificar si el dispositivo dueño del sensor está activo
            from src.Model.model import sensores, dispositivos
            sensor_db = db.query(sensores).filter(sensores.nombre == data.sensor).first()
            dispositivo = None
            if sensor_db:
                dispositivo = db.query(dispositivos).filter(dispositivos.id_dispositivo == sensor_db.id_dispositivo).first()
            else:
                # Si el sensor no existe en la BD, buscar el dispositivo por el tópico de publicación
                dispositivo = db.query(dispositivos).filter(dispositivos.topic_pub == msg.topic).first()

            if dispositivo and not dispositivo.funcionamiento_activo:
                print(f"[PAUSED] Dispositivo '{dispositivo.nombre}' desactivado por el usuario. Descartando telemetría de tanque.")
                return

            crud.crear_telemetria_tanque(
                db=db,
                sensor=data.sensor,
                distancia_cm=data.distancia_cm,
                estado_bomba=data.estado_bomba,
                fecha=data.fecha,
                id_dispositivo=dispositivo.id_dispositivo if dispositivo else None,
            )
            print("[OK] Telemetría de tanque guardada en PostgreSQL")
        else:
            print(f"[WARNING] Tópico no manejado: {msg.topic}")

    except json.JSONDecodeError:
        print(f"[ERROR] Payload MQTT inválido en {msg.topic}")
    except Exception as e:
        print(f"[ERROR] Procesando mensaje MQTT: {e}")
    finally:
        db.close()


def on_connect(client: mqtt.Client, userdata: Any, flags: dict[str, Any], rc: int, _properties: Any = None) -> None:
    """Callback al conectar al broker MQTT."""
    if rc == 0:
        print(f"[OK] Conectado a MQTT broker {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_RIEGO_DATOS, qos=1)
        client.subscribe(MQTT_TOPIC_CONTROL_AGUA, qos=1)
        print(f"   Suscrito a: {MQTT_TOPIC_RIEGO_DATOS}, {MQTT_TOPIC_CONTROL_AGUA}")
    else:
        print(f"[ERROR] Conexión MQTT falló con código: {rc}")


def start_mqtt() -> mqtt.Client | None:
    """Inicia el cliente MQTT con TLS y credenciales desde .env."""
    global _mqtt_client

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
            print("[OK] TLS habilitado para MQTT")
        except Exception as e:
            print(f"Advertencia: TLS setup falló ({e}); continuando sin validar certificado")

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        _mqtt_client = client
        print(f"[MQTT] Cliente iniciado (async)")
        return client
    except Exception as e:
        print(f"[ERROR] Iniciando cliente MQTT: {e}")
        return None


def stop_mqtt() -> None:
    """Detiene el cliente MQTT."""
    global _mqtt_client

    if _mqtt_client is None:
        return

    try:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()
        _mqtt_client = None
        print("[OK] Cliente MQTT detenido")
    except Exception as e:
        print(f"Advertencia al detener MQTT: {e}")