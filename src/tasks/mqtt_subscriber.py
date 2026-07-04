import json
import os
import logging
import time
import threading
from typing import Any

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from src.core.config import IS_PRODUCTION

from src.services.repositories import telemetria as telemetria_repository
from src.db.database import SessionLocal
from src.schemas.telemetria import TelemetriaTanqueModel, RiegoDatosModel
from src.schemas.ml import PrediccionRiegoModel

logger = logging.getLogger(__name__)
from src.api.routers.ml import obtener_prediccion_riego

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
ML_IRRIGATION_COOLDOWN_MINUTES = max(
    1, int(os.getenv("ML_IRRIGATION_COOLDOWN_MINUTES", "60"))
)

_mqtt_client: mqtt.Client | None = None


def publish_mqtt_message(topic: str, payload: str, qos: int = 1, retain: bool = False) -> None:
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


import datetime
from src.services.notifications.alert_engine import evaluar_y_disparar_alerta


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    """Procesa mensajes MQTT y guarda en PostgreSQL según el tópico."""
    db = SessionLocal()
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        logger.debug("Mensaje MQTT recibido", extra={"topic": msg.topic})

        if msg.topic == MQTT_TOPIC_RIEGO_DATOS:
            data = RiegoDatosModel(**payload)

            # Resolver la asignación primero antes de guardar para verificar si está activa
            from src.db.models import asignaciones_iot
            asig = db.query(asignaciones_iot).filter(
                asignaciones_iot.id == data.humedad_suelo.id_asignacion
            ).first()

            telemetria_repository.crear_datos_riego(db, data)
            logger.debug("Datos de riego almacenados")

            # Touch device ping
            from src.services.device_health import touch_device_by_assignment
            touch_device_by_assignment(db, data.humedad_suelo.id_asignacion)
 
            # EVALUAR ALERTAS DE SUELO Y AMBIENTE
            try:
                if data.humedad_suelo.id_asignacion and data.humedad_suelo.porcentaje is not None:
                    evaluar_y_disparar_alerta(db, data.humedad_suelo.id_asignacion, 'HUM_SUELO', float(data.humedad_suelo.porcentaje))
                if data.humedad_ambiente.id_asignacion and data.humedad_ambiente.porcentaje is not None:
                    evaluar_y_disparar_alerta(db, data.humedad_ambiente.id_asignacion, 'HUM_AMB', float(data.humedad_ambiente.porcentaje))
                if data.temperatura_ambiente.id_asignacion and data.temperatura_ambiente.temperatura is not None:
                    evaluar_y_disparar_alerta(db, data.temperatura_ambiente.id_asignacion, 'TEMP_AMB', float(data.temperatura_ambiente.temperatura))
                if data.temperatura_suelo.id_asignacion and data.temperatura_suelo.temperatura is not None:
                    evaluar_y_disparar_alerta(db, data.temperatura_suelo.id_asignacion, 'TEMP_SUELO', float(data.temperatura_suelo.temperatura))
            except Exception as eval_exc:
                logger.info(f"[ERROR] Evaluando alertas de telemetría: {eval_exc}")

            if asig and not asig.activo:
                logger.debug("Asignación inactiva; se omite inferencia", extra={"assignment_id": asig.id})
                return

            # Enviar los valores al modelo ML para obtener decisión de riego
            try:
                dispositivo = asig.dispositivo if asig else None
                id_usuario = dispositivo.id_usuario if dispositivo else None
                if not id_usuario:
                    from src.db.models import usuarios
                    primer_usuario = db.query(usuarios).order_by(usuarios.id_usuario.asc()).first()
                    if primer_usuario:
                        id_usuario = primer_usuario.id_usuario

                # Verificar si el modo de control Predictivo (ML) está activo (cultivo_modelo.activo == True)
                id_cultivo = asig.id_cultivo if asig else None
                if id_usuario and id_cultivo:
                    from src.db.models import cultivo_modelo
                    usr_mod = db.query(cultivo_modelo).filter(
                        cultivo_modelo.id_usuario == id_usuario,
                        cultivo_modelo.id_cultivo == id_cultivo,
                        cultivo_modelo.activo == True
                    ).first()
                    if not usr_mod:
                        logger.info(f"[CONTROL] El modo Predictivo (ML) no está activo para el cultivo {id_cultivo} del usuario {id_usuario}. Saltando inferencia y control automático de ML.")
                        return
                else:
                    logger.info(f"[CONTROL] No se resolvió id_usuario o id_cultivo. Saltando control automático de ML.")
                    return

                # Limitar el riego automatico a una sesion por cultivo y por hora.
                from src.db.models import riego, asignaciones_iot
                tiempo_cooldown = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(
                    minutes=ML_IRRIGATION_COOLDOWN_MINUTES
                )
                riego_reciente = db.query(riego).join(
                    asignaciones_iot,
                    riego.id_asignacion == asignaciones_iot.id,
                ).filter(
                    asignaciones_iot.id_cultivo == id_cultivo,
                    riego.id_usuario == id_usuario,
                    riego.tipo_riego == "automatico_ml",
                    riego.fecha >= tiempo_cooldown,
                ).first()
                if riego_reciente:
                    logger.info(
                        "[CONTROL] Cooldown ML activo. "
                        f"Ultimo riego: {riego_reciente.fecha}; "
                        f"intervalo: {ML_IRRIGATION_COOLDOWN_MINUTES} minutos."
                    )
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
                logger.debug("Inferencia ML completada", extra={"result": resultado.get("riego")})

                # Una recomendacion positiva abre una sesion con tiempo maximo del rele.
                # Una prediccion negativa no apaga otro evento que ya este en curso.
                if int(resultado.get("riego", 0)) == 1:
                    try:
                        from src.db.models import predicciones_ml
                        from src.services.irrigation import find_pump_assignment, start_irrigation

                        pump_assignment = find_pump_assignment(db, id_usuario, id_cultivo)
                        if pump_assignment is None:
                            raise ValueError("No existe una bomba activa asignada al cultivo.")
                        prediction = db.query(predicciones_ml).filter(
                            predicciones_ml.id_usuario == id_usuario,
                            predicciones_ml.id_cultivo == id_cultivo,
                        ).order_by(predicciones_ml.id_prediccion.desc()).first()
                        session = start_irrigation(
                            db,
                            pump_assignment,
                            "automatico_ml",
                            model_id=usr_mod.id_modelo,
                            prediction_id=prediction.id_prediccion if prediction else None,
                        )
                        logger.info(
                            f"[MQTT] Riego ML iniciado; rele autorizado por "
                            f"{session.duracion_segundos} segundos."
                        )
                    except Exception as pub_exc:
                        db.rollback()
                        logger.info(f"[ERROR] Iniciando riego ML: {pub_exc}")

            except Exception as ml_exc:
                logger.info(f"[ERROR] Al invocar ML para predicción: {ml_exc}")

        elif msg.topic == MQTT_TOPIC_CONTROL_AGUA:
            data = TelemetriaTanqueModel(**payload)

            # Verificar si el dispositivo de la asignación está activo
            from src.db.models import asignaciones_iot
            asig = db.query(asignaciones_iot).filter(
                asignaciones_iot.id == data.id_asignacion
            ).first()

            registro_tanque = telemetria_repository.crear_telemetria_tanque(
                db=db,
                id_asignacion=data.id_asignacion,
                distancia_cm=data.distancia_cm,
                estado_bomba=data.estado_bomba,
                valvula_abierta=data.valvula_abierta,
                motivo_cierre=data.motivo_cierre,
                duracion_objetivo_seg=data.duracion_objetivo_seg,
                tiempo_ejecutado_seg=data.tiempo_ejecutado_seg,
                fecha=data.fecha,
            )
            logger.debug("Telemetría de tanque almacenada")

            # Touch device ping
            from src.services.device_health import touch_device_by_assignment
            touch_device_by_assignment(db, data.id_asignacion)

            # EVALUAR ALERTA DE TANQUE BAJO
            try:
                if registro_tanque and registro_tanque.porcentaje_nivel is not None:
                    evaluar_y_disparar_alerta(db, data.id_asignacion, 'NIVEL_AGUA', float(registro_tanque.porcentaje_nivel))
            except Exception as eval_exc:
                logger.info(f"[ERROR] Evaluando alertas de tanque: {eval_exc}")

        elif msg.topic.endswith("/config/req"):
            # Determinar client_id
            parts = msg.topic.split("/")
            if len(parts) >= 3:
                client_id = parts[2]
            else:
                client_id = "ESP32_Yaku_002"

            from src.db.models import asignaciones_iot, fuentes_agua, dispositivos
            id_asignacion = payload.get("id_asignacion")
            device = db.query(dispositivos).filter(
                dispositivos.client_id_mqtt == (payload.get("client_id") or client_id)
            ).first()
            if id_asignacion:
                asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == id_asignacion).first()
            elif device:
                asig = db.query(asignaciones_iot).filter(
                    asignaciones_iot.id_dispositivo == device.id_dispositivo,
                    asignaciones_iot.activo == True,
                ).first()
                if asig is None:
                    asig = db.query(asignaciones_iot).filter(
                        asignaciones_iot.id_dispositivo == device.id_dispositivo,
                    ).order_by(asignaciones_iot.id.desc()).first()
            else:
                asig = None
            if asig:
                # Touch device ping
                from src.services.device_health import touch_device_ping
                touch_device_ping(db, device or asig.dispositivo)

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
                    if otro_asig is None:
                        # Buscar en cualquier asignacion (incluso inactiva) del mismo dispositivo
                        otro_asig = db.query(asignaciones_iot).filter(
                            asignaciones_iot.id_dispositivo == asig.id_dispositivo,
                            asignaciones_iot.id_fuente_agua != None
                        ).first()
                    if otro_asig:
                        fuente = db.query(fuentes_agua).filter(fuentes_agua.id == otro_asig.id_fuente_agua).first()

                altura_total_cm = 50.0
                distancia_seguridad_cm = 10.0
                if fuente:
                    altura_total_cm = float(fuente.altura_tanque_cm or 50.0)
                    distancia_seguridad_cm = float(fuente.altura_seguridad_cm or 10.0)

                distancia_sin_agua_cm = max(0.0, altura_total_cm - distancia_seguridad_cm)
                distancia_abrir_valvula_cm = distancia_sin_agua_cm
                distancia_cerrar_valvula_cm = max(0.0, altura_total_cm * 0.10)

                # 2. Obtener funcionamiento activo de la asignación
                funcionamiento_activo = asig.activo

                # 3. Determinar modo de riego actual
                from src.db.models import cultivo_modelo, programacion_riego
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

                asignaciones = db.query(asignaciones_iot).filter(
                    asignaciones_iot.id_dispositivo == asig.id_dispositivo,
                ).all()
                mapa_asignaciones = {
                    item.tipo_metrica.codigo: item.id
                    for item in asignaciones
                    if item.tipo_metrica is not None
                }
                if "NIVEL_AGUA" not in mapa_asignaciones and asignaciones:
                    actuador = next(
                        (
                            item for item in asignaciones
                            if item.componente and item.componente.modelo and
                            item.componente.modelo.categoria == "actuador"
                        ),
                        None
                    )
                    mapa_asignaciones["NIVEL_AGUA"] = (actuador or asignaciones[0]).id

                # 4. Responder via MQTT
                response_payload = {
                    "funcionamiento_activo": funcionamiento_activo,
                    "altura_total_cm": altura_total_cm,
                    "altura_seguridad_cm": distancia_seguridad_cm,
                    "distancia_sin_agua_cm": distancia_sin_agua_cm,
                    "distancia_abrir_valvula_cm": distancia_abrir_valvula_cm,
                    "distancia_cerrar_valvula_cm": distancia_cerrar_valvula_cm,
                    "modo": modo_actual,
                    "topic_pub": asig.dispositivo.topic_pub,
                    "topic_sub": asig.dispositivo.topic_sub or "yaku/riego/comando",
                    "asignaciones": mapa_asignaciones,
                }
                response_topic = f"yaku/dispositivo/{client_id}/config"
                client.publish(response_topic, json.dumps(response_payload), qos=1, retain=True)
                logger.debug("Configuración MQTT respondida", extra={"client_id": client_id})
            else:
                logger.info(f"[MQTT] Dispositivo o asignacion no encontrado para config req: {client_id}")
        else:
            logger.info(f"[WARNING] Topico no manejado: {msg.topic}")

    except json.JSONDecodeError:
        logger.info(f"[ERROR] Payload MQTT inválido en {msg.topic}")
    except Exception:
        logger.exception("Error procesando mensaje MQTT")
    finally:
        db.close()


def on_connect(client: mqtt.Client, userdata: Any, flags: dict[str, Any], rc: int, _properties: Any = None) -> None:
    """Callback al conectar al broker MQTT."""
    if rc == 0:
        logger.info(f"[OK] Conectado a MQTT broker {MQTT_HOST}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC_RIEGO_DATOS, qos=1)
        client.subscribe(MQTT_TOPIC_CONTROL_AGUA, qos=1)
        client.subscribe("yaku/dispositivo/+/config/req", qos=1)
        logger.info(f"   Suscrito a: {MQTT_TOPIC_RIEGO_DATOS}, {MQTT_TOPIC_CONTROL_AGUA}, yaku/dispositivo/+/config/req")
    else:
        logger.info(f"[ERROR] Conexión MQTT falló con código: {rc}")


def start_mqtt() -> mqtt.Client | None:
    """Inicia el cliente MQTT con TLS y credenciales desde .env."""
    global _mqtt_client

    if IS_PRODUCTION and (not MQTT_TLS_ENABLED or not MQTT_USERNAME or not MQTT_PASSWORD):
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
            logger.info(f"Advertencia: TLS setup falló ({e}); continuando sin validar certificado")

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
            logger.warning("Timeout deteniendo el loop MQTT; se continuara con el apagado")
            return

        logger.info("[OK] Cliente MQTT detenido")
    except Exception as e:
        logger.info(f"Advertencia al detener MQTT: {e}")
