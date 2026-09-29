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

# Reenvio de configuracion a equipos que publican con ids obsoletos: como mucho
# uno por dispositivo cada REENVIO_CONFIG_SEG (llegan lecturas cada pocos segundos).
REENVIO_CONFIG_SEG = 60
_ultimo_reenvio_config: dict[int, float] = {}

MOTIVOS_REINICIO_ANOMALO = {"BROWNOUT", "PANIC", "INT_WDT", "TASK_WDT", "WDT"}


def _descartar_si_asignacion_obsoleta(db, asig) -> bool:
    """True si la lectura llega con una asignacion de un titular anterior.

    Tras reasignar un dispositivo, el ESP32 sigue usando los ids guardados en
    su NVS hasta recibir la nueva configuracion. Antes esas lecturas se
    guardaban en la asignacion vieja (historial del agricultor anterior) y el
    nuevo no veia nada. Ahora se descartan y se le reenvia la configuracion.
    """
    if asig.activo:
        return False
    from src.main.repositories.dispositivoRep import queryAsignacionesVigentesDispositivo

    vigentes = queryAsignacionesVigentesDispositivo(db, asig.id_dispositivo)
    if any(item.id == asig.id for item in vigentes):
        return False

    logger.warning(
        "[MQTT] Telemetria descartada: la asignacion %s pertenece a un titular anterior "
        "del dispositivo %s. Se reenvia la configuracion vigente.",
        asig.id,
        asig.id_dispositivo,
    )
    import time

    ahora = time.monotonic()
    ultimo = _ultimo_reenvio_config.get(asig.id_dispositivo)
    if ultimo is None or ahora - ultimo >= REENVIO_CONFIG_SEG:
        _ultimo_reenvio_config[asig.id_dispositivo] = ahora
        from src.main.service.deviceConfigServ import publicar_config_dispositivo

        publicar_config_dispositivo(db, asig.dispositivo)
    return True


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
                # Antes esto se registraba en debug y el descarte pasaba inadvertido. Causa
                # tipica: OTRO backend (con otra BD) conectado al mismo broker respondio el
                # /config/req del colector con SUS ids de asignacion (retenidos), y el equipo
                # publica con ids que en esta BD no existen.
                logger.warning(
                    "[MQTT] Telemetria descartada: las asignaciones %s no existen en esta base "
                    "de datos. Si el equipo recibio otra configuracion, verifique que no haya "
                    "otro backend conectado al mismo broker MQTT.",
                    [
                        data.humedad_suelo.id_asignacion,
                        data.temperatura_suelo.id_asignacion,
                        data.humedad_ambiente.id_asignacion,
                        data.temperatura_ambiente.id_asignacion,
                    ],
                )
                return

            if _descartar_si_asignacion_obsoleta(db, asig):
                return

            lecturas_en_vivo = telemetria_repository.crear_datos_riego(db, data)
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
                # El dueño de la lectura es el de SU asignacion; dispositivo.id_usuario
                # recorre todas las asignaciones y podia devolver al titular anterior.
                id_usuario = asig.id_usuario if asig else None
                if not id_usuario:
                    primer_usuario = data_repository.queryProcesarMensajePrimerUsuario(
                        db
                    )
                    if primer_usuario:
                        id_usuario = primer_usuario.id_usuario

                id_cultivo = asig.id_cultivo if asig else None
                if id_usuario and id_cultivo:
                    # La caché del dashboard (15 s) quedaría desfasada respecto
                    # a la lectura que se acaba de guardar.
                    from src.main.core.cache import backend_cache

                    backend_cache.invalidate(f"dashboard_data:{id_usuario}")
                    # Las lecturas viajan en el propio evento: el dashboard
                    # las aplica al instante sin recargar todos los datos.
                    broadcast_ws_event(
                        {
                            "tipo": "control_update",
                            "event": "telemetria",
                            "id_cultivo": id_cultivo,
                            "id_usuario": id_usuario,
                            "lecturas": lecturas_en_vivo or {},
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

            if _descartar_si_asignacion_obsoleta(db, asig):
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
                    id_riego=data.id_riego,
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

            device = data_repository.queryProcesarMensajeDevice(db, client_id, payload)
            if device is None and payload.get("id_asignacion"):
                asig = data_repository.queryProcesarMensajeAsig3(
                    db, payload.get("id_asignacion")
                )
                device = asig.dispositivo if asig else None
            if device:
                # Touch device ping
                from src.main.service.deviceHealthServ import touch_device_ping

                touch_device_ping(db, device)

                # Firmware >= S3 1.0.4 informa por que se reinicio. En campo no hay
                # monitor serie: un BROWNOUT (fuente que cae al transmitir) o un
                # PANIC/WDT solo se notaban como "dejo de enviar datos".
                motivo = str(payload.get("reset") or "").upper()
                if motivo in MOTIVOS_REINICIO_ANOMALO:
                    from src.main.service.networkLogServ import registrar_evento_red

                    logger.warning(
                        "[MQTT] %s se reinicio por %s (fw %s, rssi %s)",
                        client_id, motivo, payload.get("fw"), payload.get("rssi"),
                    )
                    registrar_evento_red(
                        "dispositivo_reinicio_anomalo",
                        f"{device.nombre} ({client_id}) se reinicio por {motivo}"
                        + (
                            ": caida de tension, revise la fuente de alimentacion."
                            if motivo == "BROWNOUT"
                            else "."
                        ),
                    )

                # Configuracion del titular ACTUAL (no la del id que traiga el
                # equipo, que puede ser de un agricultor anterior).
                from src.main.service.deviceConfigServ import (
                    construir_config_dispositivo,
                )

                response_payload = construir_config_dispositivo(db, device)
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
