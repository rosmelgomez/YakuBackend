import json
import os
from typing import Any

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from src.Model import crud
from src.Model.conexion import SessionLocal
from src.Model.model import humedad_ambiente, humedad_suelo, temperatura_ambiente, temperatura_suelo
from src.Model.schemas import ControlAguaModel, RiegoDatosModel, PrediccionRiegoModel
from src.Router.ml_router import predecir_riego

load_dotenv()

# ── Credenciales desde .env con HiveMQ Cloud ──────────────────────
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC_RIEGO_DATOS = os.getenv("MQTT_TOPIC_RIEGO_DATOS", "yaku/riego/datos")
MQTT_TOPIC_CONTROL_CMD = os.getenv("MQTT_TOPIC_CONTROL_CMD", "yaku/riego/comando")
MQTT_TOPIC_CONTROL_AGUA = os.getenv("MQTT_TOPIC_CONTROL_AGUA", "yaku/riego/control_agua")
MQTT_TLS_ENABLED = os.getenv("MQTT_TLS_ENABLED", "true").lower() in {"1", "true", "yes"}
MQTT_TLS_CA_CERT = os.getenv("MQTT_TLS_CA_CERT", "")

_mqtt_client: mqtt.Client | None = None


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    """Procesa mensajes MQTT y guarda en PostgreSQL según el tópico."""
    db = SessionLocal()
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        print(f"📥 MQTT recibido en {msg.topic}: {payload}")

        if msg.topic == MQTT_TOPIC_RIEGO_DATOS:
            data = RiegoDatosModel(**payload)
            crud.crear_datos_riego(
                db,
                humedad_suelo(
                    sensor=data.humedad_suelo.sensor,
                    valor=data.humedad_suelo.valor,
                    porcentaje=data.humedad_suelo.porcentaje,
                    fecha=data.humedad_suelo.fecha,
                ),
                humedad_ambiente(
                    sensor=data.humedad_ambiente.sensor,
                    valor=data.humedad_ambiente.valor,
                    porcentaje=data.humedad_ambiente.porcentaje,
                    fecha=data.humedad_ambiente.fecha,
                ),
                temperatura_ambiente(
                    sensor=data.temperatura_ambiente.sensor,
                    valor=data.temperatura_ambiente.valor,
                    temperatura=data.temperatura_ambiente.temperatura,
                    fecha=data.temperatura_ambiente.fecha,
                ),
                temperatura_suelo(
                    sensor=data.temperatura_suelo.sensor,
                    valor=data.temperatura_suelo.valor,
                    temperatura=data.temperatura_suelo.temperatura,
                    fecha=data.temperatura_suelo.fecha,
                ),
            )
            print("✅ Datos de riego guardados en PostgreSQL")

            # Enviar los valores al modelo ML para obtener decisión de riego
            try:
                pred_input = PrediccionRiegoModel(
                    humedad_suelo=float(data.humedad_suelo.valor),
                    humedad_ambiente=float(data.humedad_ambiente.valor),
                    temperatura_ambiente=float(data.temperatura_ambiente.temperatura),
                    temperatura_suelo=float(data.temperatura_suelo.temperatura),
                )
                resultado = predecir_riego(pred_input)
                print(f"🧠 Resultado ML: {resultado}")

                # Publicar comando de control al ESP32 (ON/OFF)
                try:
                    comando = "ON" if int(resultado.get("riego", 0)) == 1 else "OFF"
                    client.publish(MQTT_TOPIC_CONTROL_CMD, comando, qos=1, retain=True)
                    print(f"📤 Publicado comando '{comando}' en {MQTT_TOPIC_CONTROL_CMD}")
                except Exception as pub_exc:
                    print(f"❌ Error publicando comando MQTT: {pub_exc}")

            except Exception as ml_exc:
                print(f"❌ Error al invocar ML para predicción: {ml_exc}")

        elif msg.topic == MQTT_TOPIC_CONTROL_AGUA:
            data = ControlAguaModel(**payload)
            crud.crear_control_agua(
                db=db,
                sensor=data.sensor,
                distancia_cm=data.distancia_cm,
                altura_referencia_cm=data.altura_referencia_cm,
                estado_bomba=data.estado_bomba,
                fecha=data.fecha,
            )
            print("✅ Control de agua guardado en PostgreSQL")
        else:
            print(f"⚠️ Tópico no manejado: {msg.topic}")

    except json.JSONDecodeError:
        print(f"❌ Payload MQTT inválido en {msg.topic}")
    except Exception as e:
        print(f"❌ Error procesando mensaje MQTT: {e}")
    finally:
        db.close()


def on_connect(client: mqtt.Client, userdata: Any, flags: dict[str, Any], rc: int, _properties: Any = None) -> None:
    """Callback al conectar al broker MQTT."""
    if rc == 0:
        print(f"✅ Conectado a MQTT broker {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_RIEGO_DATOS, qos=1)
        client.subscribe(MQTT_TOPIC_CONTROL_AGUA, qos=1)
        print(f"   Suscrito a: {MQTT_TOPIC_RIEGO_DATOS}, {MQTT_TOPIC_CONTROL_AGUA}")
    else:
        print(f"❌ Error de conexión MQTT: {rc}")


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
            print("✅ TLS habilitado para MQTT")
        except Exception as e:
            print(f"Advertencia: TLS setup falló ({e}); continuando sin validar certificado")

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        _mqtt_client = client
        print(f"🔄 Cliente MQTT iniciado (async)")
        return client
    except Exception as e:
        print(f"❌ Error iniciando cliente MQTT: {e}")
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
        print("✅ Cliente MQTT detenido")
    except Exception as e:
        print(f"Advertencia al detener MQTT: {e}")