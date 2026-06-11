import json
import os
from typing import Any

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from src.services import crud
from src.models.database import SessionLocal
from src.schemas.schemas import TelemetriaTanqueModel, RiegoDatosModel, PrediccionRiegoModel
from src.routers.ml import obtener_prediccion_riego

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
            data = RiegoDatosModel(**payload)

            # Resolver la asignación primero antes de guardar para verificar si está activa
            from src.models.models import asignaciones_iot
            asig = db.query(asignaciones_iot).filter(
                asignaciones_iot.id == data.humedad_suelo.id_asignacion
            ).first()

            crud.crear_datos_riego(db, data)
            print("[OK] Datos de riego guardados en PostgreSQL")
 
            if asig and not asig.activo:
                print(f"[PAUSED] Asignación '{asig.id}' inactiva. Saltando control e inferencia.")
                return

            # Enviar los valores al modelo ML para obtener decisión de riego
            try:
                dispositivo = asig.dispositivo if asig else None
                id_usuario = dispositivo.id_usuario if dispositivo else None
                if not id_usuario:
                    from src.models.models import usuarios
                    primer_usuario = db.query(usuarios).order_by(usuarios.id_usuario.asc()).first()
                    if primer_usuario:
                        id_usuario = primer_usuario.id_usuario

                # Verificar si el modo de control Predictivo (ML) está activo (cultivo_modelo.activo == True)
                id_cultivo = asig.id_cultivo if asig else None
                if id_usuario and id_cultivo:
                    from src.models.models import cultivo_modelo
                    usr_mod = db.query(cultivo_modelo).filter(
                        cultivo_modelo.id_usuario == id_usuario,
                        cultivo_modelo.id_cultivo == id_cultivo,
                        cultivo_modelo.activo == True
                    ).first()
                    if not usr_mod:
                        print(f"[CONTROL] El modo Predictivo (ML) no está activo para el cultivo {id_cultivo} del usuario {id_usuario}. Saltando inferencia y control automático de ML.")
                        return
                else:
                    print(f"[CONTROL] No se resolvió id_usuario o id_cultivo. Saltando control automático de ML.")
                    return

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
                    id_dispositivo=id_dispositivo,
                    id_cultivo=id_cultivo,
                    persistir=True
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

            # Verificar si el dispositivo de la asignación está activo
            from src.models.models import asignaciones_iot
            asig = db.query(asignaciones_iot).filter(
                asignaciones_iot.id == data.id_asignacion
            ).first()

            crud.crear_telemetria_tanque(
                db=db,
                id_asignacion=data.id_asignacion,
                distancia_cm=data.distancia_cm,
                estado_bomba=data.estado_bomba,
                motivo_cierre=data.motivo_cierre,
                fecha=data.fecha,
            )
            print("[OK] Telemetría de tanque guardada en PostgreSQL")
        elif msg.topic.endswith("/config/req"):
            # Determinar client_id
            parts = msg.topic.split("/")
            if len(parts) >= 3:
                client_id = parts[2]
            else:
                client_id = "ESP32_Yaku_002"

            id_asignacion = payload.get("id_asignacion")
            if not id_asignacion:
                print(f"[MQTT] Falta id_asignacion en peticion de config")
                return

            # Consultar base de datos
            from src.models.models import asignaciones_iot, fuentes_agua, dispositivos
            asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == id_asignacion).first()
            if asig:
                # 1. Obtener fuente de agua
                fuente = None
                if asig.id_fuente_agua is not None:
                    fuente = db.query(fuentes_agua).filter(fuentes_agua.id == asig.id_fuente_agua).first()
                
                if fuente is None:
                    # Buscar en cualquier asignacion activa del mismo dispositivo
                    otro_asig = db.query(asignaciones_iot).filter(
                        asignaciones_iot.id_dispositivo == asig.id_dispositivo,
                        asignaciones_iot.id_fuente_agua != None,
                        asignaciones_iot.activo == True
                    ).first()
                    if otro_asig:
                        fuente = db.query(fuentes_agua).filter(fuentes_agua.id == otro_asig.id_fuente_agua).first()

                altura_total_cm = 50.0
                distancia_sin_agua_cm = 45.0
                if fuente:
                    altura_total_cm = float(fuente.altura_tanque_cm or 50.0)
                    distancia_sin_agua_cm = float(fuente.altura_seguridad_cm or (altura_total_cm - 5.0))

                # 2. Obtener funcionamiento activo de la asignación
                funcionamiento_activo = asig.activo

                # 3. Determinar modo de riego actual
                from src.models.models import cultivo_modelo, programacion_riego
                usr_mod = db.query(cultivo_modelo).filter(
                    cultivo_modelo.id_usuario == asig.id_usuario,
                    cultivo_modelo.id_cultivo == asig.id_cultivo,
                    cultivo_modelo.activo == True
                ).first()

                prog_act = db.query(programacion_riego).filter(
                    programacion_riego.id_asignacion == asig.id,
                    programacion_riego.activo == True
                ).first() is not None

                modo_actual = "manual"
                if usr_mod:
                    modo_actual = "predictivo"
                elif prog_act:
                    modo_actual = "programado"

                # 4. Responder via MQTT
                response_payload = {
                    "funcionamiento_activo": funcionamiento_activo,
                    "altura_total_cm": altura_total_cm,
                    "distancia_sin_agua_cm": distancia_sin_agua_cm,
                    "modo": modo_actual,
                    "topic_sub": asig.dispositivo.topic_sub or "yaku/riego/comando"
                }
                response_topic = f"yaku/dispositivo/{client_id}/config"
                client.publish(response_topic, json.dumps(response_payload), qos=1, retain=True)
                print(f"[MQTT] Respondida config para {client_id} en {response_topic}: {response_payload}")
            else:
                print(f"[MQTT] Asignacion {id_asignacion} no encontrada para config req")
        else:
            print(f"[WARNING] Topico no manejado: {msg.topic}")

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
        client.subscribe("yaku/dispositivo/+/config/req", qos=1)
        print(f"   Suscrito a: {MQTT_TOPIC_RIEGO_DATOS}, {MQTT_TOPIC_CONTROL_AGUA}, yaku/dispositivo/+/config/req")
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