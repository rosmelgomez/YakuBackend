from src.main.core.waterSource import source_firmware_config
import datetime
import json
import logging
from typing import Any

import paho.mqtt.client as mqtt

from src.main.core.mqttConfig import (
    ML_IRRIGATION_COOLDOWN_MINUTES,
    MQTT_TOPIC_CONTROL_AGUA,
    MQTT_TOPIC_RIEGO_DATOS,
)
from src.main.db.databaseConexion import SessionLocal
from src.main.dtos.mlDto import PrediccionRiegoModel
from src.main.dtos.telemetriaDto import RiegoDatosModel, TelemetriaTanqueModel
from src.main.repositories import mqttRep as data_repository
from src.main.repositories import sessionRep as session_repository
from src.main.repositories import telemetriaRep as telemetria_repository
from src.main.service import telemetriaServ as telemetria_service
from src.main.service.mlServ import obtener_prediccion_riego
from src.main.service.notifications.alertEngineServ import evaluar_y_disparar_alerta

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

            # Resolver la asignación primero antes de guardar para verificar si está activa
            asig = data_repository.queryProcesarMensajeAsig(db, data)

            telemetria_repository.crear_datos_riego(db, data)
            logger.debug("Datos de riego almacenados")

            # Touch device ping
            from src.main.service.deviceHealthServ import touch_device_by_assignment

            touch_device_by_assignment(db, data.humedad_suelo.id_asignacion)

            # EVALUAR ALERTAS DE SUELO Y AMBIENTE
            try:
                if (
                    data.humedad_suelo.id_asignacion
                    and data.humedad_suelo.porcentaje is not None
                ):
                    evaluar_y_disparar_alerta(
                        db,
                        data.humedad_suelo.id_asignacion,
                        "HUM_SUELO",
                        float(data.humedad_suelo.porcentaje),
                    )
                if (
                    data.humedad_ambiente.id_asignacion
                    and data.humedad_ambiente.porcentaje is not None
                ):
                    evaluar_y_disparar_alerta(
                        db,
                        data.humedad_ambiente.id_asignacion,
                        "HUM_AMB",
                        float(data.humedad_ambiente.porcentaje),
                    )
                if (
                    data.temperatura_ambiente.id_asignacion
                    and data.temperatura_ambiente.temperatura is not None
                ):
                    evaluar_y_disparar_alerta(
                        db,
                        data.temperatura_ambiente.id_asignacion,
                        "TEMP_AMB",
                        float(data.temperatura_ambiente.temperatura),
                    )
                if (
                    data.temperatura_suelo.id_asignacion
                    and data.temperatura_suelo.temperatura is not None
                ):
                    evaluar_y_disparar_alerta(
                        db,
                        data.temperatura_suelo.id_asignacion,
                        "TEMP_SUELO",
                        float(data.temperatura_suelo.temperatura),
                    )
            except Exception as eval_exc:
                logger.info(f"[ERROR] Evaluando alertas de telemetría: {eval_exc}")

            if asig and not asig.activo:
                logger.debug(
                    "Asignación inactiva; se omite inferencia",
                    extra={"assignment_id": asig.id},
                )
                return

            # Enviar los valores al modelo ML para obtener decisión de riego
            try:
                dispositivo = asig.dispositivo if asig else None
                id_usuario = dispositivo.id_usuario if dispositivo else None
                if not id_usuario:
                    primer_usuario = data_repository.queryProcesarMensajePrimerUsuario(
                        db
                    )
                    if primer_usuario:
                        id_usuario = primer_usuario.id_usuario

                # Verificar si el modo de control Predictivo (ML) está activo (cultivo_modelo.activo == True)
                id_cultivo = asig.id_cultivo if asig else None
                if id_usuario and id_cultivo:
                    usr_mod = data_repository.queryProcesarMensajeUsrMod(
                        db, id_usuario, id_cultivo
                    )
                    if not usr_mod:
                        logger.info(
                            f"[CONTROL] El modo Predictivo (ML) no está activo para el cultivo {id_cultivo} del usuario {id_usuario}. Saltando inferencia y control automático de ML."
                        )
                        return
                else:
                    logger.info(
                        f"[CONTROL] No se resolvió id_usuario o id_cultivo. Saltando control automático de ML."
                    )
                    return

                # Limitar el riego automatico a una sesion por cultivo y por hora.
                tiempo_cooldown = datetime.datetime.now(datetime.timezone.utc).replace(
                    tzinfo=None
                ) - datetime.timedelta(minutes=ML_IRRIGATION_COOLDOWN_MINUTES)
                riego_reciente = data_repository.queryProcesarMensajeRiegoReciente(
                    db, id_cultivo, id_usuario, tiempo_cooldown
                )
                if riego_reciente:
                    logger.info(
                        "[CONTROL] Cooldown ML activo. "
                        f"Ultimo riego: {riego_reciente.fecha}; "
                        f"intervalo: {ML_IRRIGATION_COOLDOWN_MINUTES} minutos."
                    )
                    return

                pred_input = PrediccionRiegoModel(
                    humedad_suelo=float(data.humedad_suelo.valor)
                    if data.humedad_suelo.valor is not None
                    else 0.0,
                    humedad_ambiente=float(data.humedad_ambiente.valor)
                    if data.humedad_ambiente.valor is not None
                    else 0.0,
                    temperatura_ambiente=float(data.temperatura_ambiente.temperatura)
                    if data.temperatura_ambiente.temperatura is not None
                    else 0.0,
                    temperatura_suelo=float(data.temperatura_suelo.temperatura)
                    if data.temperatura_suelo.temperatura is not None
                    else 0.0,
                )
                id_dispositivo = dispositivo.id_dispositivo if dispositivo else None
                resultado = obtener_prediccion_riego(
                    pred_input,
                    db,
                    id_usuario=id_usuario,
                    id_dispositivo=id_dispositivo,
                    id_cultivo=id_cultivo,
                    persistir=True,
                )
                logger.debug(
                    "Inferencia ML completada", extra={"result": resultado.get("riego")}
                )

                # Una recomendacion positiva abre una sesion con tiempo maximo del rele.
                # Una prediccion negativa no apaga otro evento que ya este en curso.
                if int(resultado.get("riego", 0)) == 1:
                    try:
                        from src.main.service.irrigationServ import (
                            find_pump_assignment,
                            start_irrigation,
                        )

                        pump_assignment = find_pump_assignment(
                            db, id_usuario, id_cultivo
                        )
                        if pump_assignment is None:
                            raise ValueError(
                                "No existe una bomba activa asignada al cultivo."
                            )
                        prediction = data_repository.queryProcesarMensajePrediction(
                            db, id_usuario, id_cultivo
                        )
                        session = start_irrigation(
                            db,
                            pump_assignment,
                            "automatico_ml",
                            model_id=usr_mod.id_modelo,
                            prediction_id=prediction.id_prediccion
                            if prediction
                            else None,
                        )
                        logger.info(
                            f"[MQTT] Riego ML iniciado; rele autorizado por "
                            f"{session.duracion_segundos} segundos."
                        )
                    except Exception as pub_exc:
                        session_repository.rollback(db)
                        logger.info(f"[ERROR] Iniciando riego ML: {pub_exc}")

            except Exception as ml_exc:
                logger.info(f"[ERROR] Al invocar ML para predicción: {ml_exc}")

        elif msg.topic == MQTT_TOPIC_CONTROL_AGUA:
            data = TelemetriaTanqueModel(**payload)

            # Verificar si el dispositivo de la asignación está activo
            asig = data_repository.queryProcesarMensajeAsig2(db, data)

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

            # Touch device ping
            from src.main.service.deviceHealthServ import touch_device_by_assignment

            touch_device_by_assignment(db, data.id_asignacion)

            # EVALUAR ALERTA DE TANQUE BAJO
            try:
                if registro_tanque and registro_tanque.porcentaje_nivel is not None:
                    evaluar_y_disparar_alerta(
                        db,
                        data.id_asignacion,
                        "NIVEL_AGUA",
                        float(registro_tanque.porcentaje_nivel),
                    )
            except Exception as eval_exc:
                logger.info(f"[ERROR] Evaluando alertas de tanque: {eval_exc}")

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

                # 3. Determinar modo de riego actual
                usr_mod = data_repository.queryProcesarMensajeUsrMod2(db, asig)

                prog_act = (
                    data_repository.queryProcesarMensajeProgramacionRiego(db, asig)
                    is not None
                )

                modo_actual = "manual"
                if usr_mod:
                    modo_actual = "predictivo"
                elif prog_act:
                    modo_actual = "programado"

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
                logger.info(
                    f"[MQTT] Dispositivo o asignacion no encontrado para config req: {client_id}"
                )
        else:
            logger.info(f"[WARNING] Topico no manejado: {msg.topic}")

    except json.JSONDecodeError:
        logger.info(f"[ERROR] Payload MQTT inválido en {msg.topic}")
    except Exception:
        logger.exception("Error procesando mensaje MQTT")
    finally:
        db.close()
