from src.main.core.waterSource import source_firmware_config
import json
import logging
from typing import Any

import paho.mqtt.client as mqtt

from src.main.core.mqttConfig import (
    MQTT_TOPIC_CONTROL_AGUA,
    MQTT_TOPIC_RIEGO_DATOS,
)
from src.main.db.databaseConexion import SessionLocal
from src.main.dtos.telemetriaDto import RiegoDatosModel, TelemetriaTanqueModel
from src.main.repositories import mqttRep as data_repository
from src.main.repositories import sessionRep as session_repository
from src.main.repositories import telemetriaRep as telemetria_repository
from src.main.service import telemetriaServ as telemetria_service
from src.main.service.notifications.websocketManagerServ import broadcast_ws_event

logger = logging.getLogger(__name__)


def procesar_mensajeServ(
    client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage
) -> None:
    """Procesa mensajes MQTT y guarda en PostgreSQL según el tópico."""
    db = SessionLocal()
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        logger.debug("Mensaje MQTT recibido", extra={"topic": msg.topic})

        if msg.topic == MQTT_TOPIC_RIEGO_DATOS:
            data = RiegoDatosModel(**payload)

            # Resolver la asignación con cualquiera de los 4 sensores del
            # mensaje. Antes solo se usaba la de humedad de suelo: si ese
            # sensor no estaba asignado (id 0), se descartaba el mensaje
            # completo y se perdian tambien las lecturas de los otros tres.
            asig = None
            for id_candidato in (
                data.humedad_suelo.id_asignacion,
                data.temperatura_suelo.id_asignacion,
                data.humedad_ambiente.id_asignacion,
                data.temperatura_ambiente.id_asignacion,
            ):
                if id_candidato:
                    asig = data_repository.queryProcesarMensajeAsig3(db, id_candidato)
                    if asig:
                        break
            if not asig:
                logger.debug(
                    "[MQTT] Ninguna asignación del mensaje de telemetría existe. Se omite el mensaje."
                )
                return

            telemetria_repository.crear_datos_riego(db, data)
            logger.debug("Datos de riego almacenados")

            # Touch device ping
            from src.main.service.deviceHealthServ import touch_device_by_assignment

            touch_device_by_assignment(db, asig.id)

            if asig and not asig.activo:
                logger.debug(
                    "Asignación inactiva; se omite notificación",
                    extra={"assignment_id": asig.id},
                )
                return

            # El riego automatico usa SIEMPRE la misma logica centralizada
            # (schedulerServ.check_ml_cooldown_and_irrigate): cooldown con el
            # id_usuario correcto, siempre guarda la prediccion, solo
            # ejecuta riego si corresponde. Antes este handler duplicaba esa
            # logica con su propio cache en memoria desincronizado del
            # scheduler, lo que permitia saltarse el cooldown y crear
            # sesiones de riego en bucle. Ahora, en vez de duplicarla, se
            # reutiliza la MISMA funcion ya corregida como disparador
            # adicional: si el dato de telemetria que se acaba de guardar ya
            # deja el cooldown cumplido, se evalua (y se riega, si
            # corresponde) de inmediato en vez de esperar al proximo tick
            # dinamico del scheduler. Si el cooldown NO esta cumplido, la
            # funcion simplemente no hace nada para ese cultivo (no genera
            # ni prediccion ni riego) -- la prediccion solo se guarda cuando
            # el cooldown ya paso y se llega a evaluar el modelo.
            try:
                from src.main.service.schedulerServ import (
                    check_ml_cooldown_and_irrigate,
                )

                check_ml_cooldown_and_irrigate(db)
            except Exception as ml_exc:
                logger.warning(f"[MQTT] Error evaluando ML tras telemetria: {ml_exc}")

            try:
                dispositivo = asig.dispositivo if asig else None
                id_usuario = dispositivo.id_usuario if dispositivo else None
                if not id_usuario:
                    primer_usuario = data_repository.queryProcesarMensajePrimerUsuario(
                        db
                    )
                    if primer_usuario:
                        id_usuario = primer_usuario.id_usuario

                id_cultivo = asig.id_cultivo if asig else None
                if id_usuario and id_cultivo:
                    broadcast_ws_event(
                        {
                            "tipo": "control_update",
                            "event": "telemetria",
                            "id_cultivo": id_cultivo,
                            "id_usuario": id_usuario,
                        },
                        id_usuario,
                    )
            except Exception as notify_exc:
                logger.info(f"[ERROR] Al notificar telemetria: {notify_exc}")

        elif msg.topic == MQTT_TOPIC_CONTROL_AGUA:
            data = TelemetriaTanqueModel(**payload)

            # Verificar si la asignación existe en base de datos
            asig = data_repository.queryProcesarMensajeAsig2(db, data)
            if not asig:
                logger.debug(
                    "[MQTT] Asignación con id %s no encontrada para telemetría de tanque. Se omite el mensaje.",
                    data.id_asignacion,
                )
                return

            try:
                registro_tanque = telemetria_service.crear_telemetria_tanque(
                    db=db,
                    id_asignacion=data.id_asignacion,
                    distancia_cm=data.distancia_cm,
                    estado_bomba=data.estado_bomba,
                    valvula_abierta=data.valvula_abierta,
                    motivo_cierre=data.motivo_cierre,
                    duracion_objetivo_seg=data.duracion_objetivo_seg,
                    tiempo_ejecutado_seg=data.tiempo_ejecutado_seg,
                    litros_riego=data.litros_riego,
                    litros_acumulados=data.litros_acumulados,
                    caudal_l_min=data.caudal_l_min,
                    pulsos_riego=data.pulsos_riego,
                    pulsos_por_litro=data.pulsos_por_litro,
                    metodo_medicion=data.metodo_medicion,
                    fecha=data.fecha,
                )
                logger.debug("Telemetría de tanque almacenada")

                if asig and asig.id_usuario:
                    broadcast_ws_event(
                        {
                            "tipo": "control_update",
                            "event": "tanque",
                            "id_cultivo": asig.id_cultivo,
                            "id_usuario": asig.id_usuario,
                        },
                        asig.id_usuario,
                    )

                # Touch device ping
                from src.main.service.deviceHealthServ import touch_device_by_assignment

                touch_device_by_assignment(db, data.id_asignacion)

            except Exception as tank_exc:
                session_repository.rollback(db)
                logger.warning(
                    f"[MQTT] Error al almacenar telemetría de tanque para asignación {data.id_asignacion}: {tank_exc}"
                )

        elif msg.topic.endswith("/config/req"):
            # Determinar client_id
            parts = msg.topic.split("/")
            if len(parts) >= 3:
                client_id = parts[2]
            else:
                client_id = "ESP32_Yaku_002"

            id_asignacion = payload.get("id_asignacion")
            device = data_repository.queryProcesarMensajeDevice(db, client_id, payload)
            if id_asignacion:
                asig = data_repository.queryProcesarMensajeAsig3(db, id_asignacion)
            elif device:
                asig = data_repository.queryProcesarMensajeAsig4(db, device)
                if asig is None:
                    asig = data_repository.queryProcesarMensajeAsig5(db, device)
            else:
                asig = None
            if asig:
                # Touch device ping
                from src.main.service.deviceHealthServ import touch_device_ping

                touch_device_ping(db, device or asig.dispositivo)

                # 1. Obtener fuente de agua
                fuente = None
                if asig.id_fuente_agua is not None:
                    fuente = data_repository.queryProcesarMensajeFuente(db, asig)

                if fuente is None:
                    # Buscar en cualquier asignacion activa del mismo dispositivo
                    otro_asig = data_repository.queryProcesarMensajeOtroAsig(db, asig)
                    if otro_asig is None:
                        # Buscar en cualquier asignacion (incluso inactiva) del mismo dispositivo
                        otro_asig = data_repository.queryProcesarMensajeOtroAsig2(
                            db, asig
                        )
                    if otro_asig:
                        fuente = data_repository.queryProcesarMensajeFuente2(
                            db, otro_asig
                        )

                if fuente is None and asig.cultivo is not None:
                    fuente = asig.cultivo.fuente_agua

                source_config = source_firmware_config(fuente)

                # 2. Obtener funcionamiento activo de la asignación
                funcionamiento_activo = asig.activo

                # 3. Determinar modo de riego actual (ML predictivo como único modo)
                modo_actual = "predictivo"
                from src.main.service.irrigationServ import (
                    obtener_litros_acumulados_asignacion,
                )
                litros_acumulados = obtener_litros_acumulados_asignacion(db, asig.id)

                asignaciones = data_repository.queryProcesarMensajeAsignaciones(
                    db, asig
                )
                mapa_asignaciones = {
                    item.tipo_metrica.codigo: item.id
                    for item in asignaciones
                    if item.tipo_metrica is not None
                }
                if asig.dispositivo.metodo_medicion != "flujometro" and "NIVEL_AGUA" not in mapa_asignaciones and asignaciones:
                    actuador = next(
                        (
                            item
                            for item in asignaciones
                            if item.componente
                            and item.componente.modelo
                            and item.componente.modelo.categoria == "actuador"
                        ),
                        None,
                    )
                    mapa_asignaciones["NIVEL_AGUA"] = (actuador or asignaciones[0]).id

                # 4. Responder via MQTT
                response_payload = {
                    "metodo_medicion": asig.dispositivo.metodo_medicion,
                    **source_config,
                    "funcionamiento_activo": funcionamiento_activo,
                    "modo": modo_actual,
                    "litros_acumulados": round(float(litros_acumulados), 2),
                    "topic_pub": asig.dispositivo.topic_pub,
                    "topic_sub": asig.dispositivo.topic_sub or "yaku/riego/comando",
                    "asignaciones": mapa_asignaciones,
                }
                response_topic = f"yaku/dispositivo/{client_id}/config"
                client.publish(
                    response_topic, json.dumps(response_payload), qos=1, retain=True
                )
                logger.debug(
                    "Configuración MQTT respondida", extra={"client_id": client_id}
                )
            else:
                logger.debug(
                    "[MQTT] Dispositivo o asignacion no encontrado para config req: %s",
                    client_id,
                )
        else:
            logger.info(f"[WARNING] Topico no manejado: {msg.topic}")

    except json.JSONDecodeError:
        logger.info(f"[ERROR] Payload MQTT inválido en {msg.topic}")
    except Exception:
        logger.exception("Error procesando mensaje MQTT")
    finally:
        db.close()
