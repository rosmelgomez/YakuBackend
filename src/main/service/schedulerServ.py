import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.main.repositories import irrigationRep as irrigation_repo
from src.main.repositories import schedulerRep as data_repository
from src.main.repositories import sessionRep as session_repository
from src.main.service.irrigationServ import (
    executed_seconds,
    find_pump_assignment,
    get_max_relay_seconds,
    planned_seconds,
    stop_irrigation,
)

logger = logging.getLogger(__name__)

# El ML se dispara desde varios hilos (scheduler, cada mensaje MQTT, boton
# manual, activacion del actuador). Sin serializar, dos evaluaciones pueden
# pasar a la vez el chequeo de "no hay riego en curso" y crear dos riegos.
ml_eval_lock = threading.Lock()

# Una lectura de humedad de suelo mas vieja que esto no representa el estado
# actual del cultivo (sensor caido o sin reportar): no se evalua con ella.
MAX_ANTIGUEDAD_HUMEDAD_SUELO_SEG = int(
    os.getenv("ML_MAX_ANTIGUEDAD_HUMEDAD_SUELO_SEG", "900")
)


def hay_riego_pendiente(db: Session, pump_assignment) -> bool:
    """True si hay un riego en curso O pausado (a medio ciclo) para este
    actuador, o si la bomba/valvula figura encendida. Un riego pausado (p.ej.
    por desconexion) sigue siendo "el ciclo actual": el ML no debe evaluar ni
    iniciar otro encima; ese ciclo se retoma al volver el dispositivo."""
    from src.main.repositories import controlRep as control_repo

    if irrigation_repo.queryStartIrrigationActive(db, pump_assignment):
        return True
    tank_config = control_repo.queryObtenerDatosControlConfigT(db, pump_assignment)
    return bool(tank_config and tank_config.bomba_encendida)


def leer_entradas_ml(db: Session, id_cultivo: int, now: datetime):
    """Lee la ultima lectura valida de cada variable del modelo.

    Devuelve (PrediccionRiegoModel, None) o (None, motivo) si falta alguna
    variable o si la humedad de suelo -- la variable dominante del modelo --
    esta desactualizada. Antes, una variable faltante se reemplazaba por 0.0:
    un sensor de suelo caido equivalia a "suelo 0% seco" y el ML regaba."""
    from src.main.dtos.mlDto import PrediccionRiegoModel
    from src.main.repositories import mlRep as ml_repository

    sensor_asigs = ml_repository.queryEjecutarPrediccionEnVivoSensorAsigs(db, id_cultivo)
    sensor_asig_ids = [sa.id for sa in sensor_asigs]
    if not sensor_asig_ids:
        return None, "El cultivo no tiene sensores activos asignados."

    h_suelo = ml_repository.queryEjecutarPrediccionEnVivoHSuelo(db, sensor_asig_ids)
    h_amb = ml_repository.queryEjecutarPrediccionEnVivoHAmb(db, sensor_asig_ids)
    t_amb = ml_repository.queryEjecutarPrediccionEnVivoTAmb(db, sensor_asig_ids)
    t_suelo = ml_repository.queryEjecutarPrediccionEnVivoTSuelo(db, sensor_asig_ids)

    faltantes = [
        nombre
        for nombre, valor in (
            ("humedad de suelo", h_suelo.valor if h_suelo else None),
            ("humedad ambiente", h_amb.valor if h_amb else None),
            ("temperatura ambiente", t_amb.temperatura if t_amb else None),
            ("temperatura de suelo", t_suelo.temperatura if t_suelo else None),
        )
        if valor is None
    ]
    if faltantes:
        return None, f"Sin lecturas válidas de: {', '.join(faltantes)}."

    if h_suelo.fecha and (now - h_suelo.fecha).total_seconds() > MAX_ANTIGUEDAD_HUMEDAD_SUELO_SEG:
        minutos = int((now - h_suelo.fecha).total_seconds() // 60)
        return None, f"La última lectura de humedad de suelo tiene {minutos} min; el sensor no está reportando."

    return (
        PrediccionRiegoModel(
            humedad_suelo=float(h_suelo.valor),
            humedad_ambiente=float(h_amb.valor),
            temperatura_ambiente=float(t_amb.temperatura),
            temperatura_suelo=float(t_suelo.temperatura),
        ),
        None,
    )


def check_durations(db: Session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Todas las formas de riego comparten el mismo limite de seguridad del rele.
    # Excluimos las sesiones que están en pausa temporal
    active_sessions = data_repository.queryCheckDurationsActiveSessions(db)

    for session in active_sessions:
        asig = data_repository.queryCheckDurationsAsig(db, session)
        if not asig:
            continue

        pump_assignment = find_pump_assignment(db, session.id_usuario, asig.id_cultivo)
        if pump_assignment is None:
            logger.info(
                "[SCHEDULER] Sesion de riego sin bomba activa asociada. Cerrando sesion huerfana. "
                f"Sesion={session.id}, asignacion={session.id_asignacion}."
            )
            try:
                stop_irrigation(db, asig, "dispositivo_desactivado", publish=False)
            except Exception:
                session_repository.rollback(db)
                logger.exception("Error cerrando sesion de riego huerfana")
                continue
            # El actuador ya no esta activo en BD, pero el equipo pudo quedar
            # regando: se le envia OFF (sin bloquear el cierre si MQTT falla).
            try:
                from src.main.service.irrigationServ import (
                    _publish_relay_command,
                    build_relay_command,
                )

                _publish_relay_command(asig, build_relay_command("OFF"))
            except Exception as exc:
                logger.warning(
                    f"No se pudo enviar OFF al actuador de la sesion huerfana {session.id}: {exc}"
                )
            continue
        maximum = get_max_relay_seconds(
            db, session.id_usuario, asig.id_cultivo
        )
        stored_duration = planned_seconds(session) or maximum
        duracion_seg = min(max(int(stored_duration), 60), maximum)

        elapsed = executed_seconds(session, now)
        if elapsed >= duracion_seg:
            logger.info(
                f"[SCHEDULER] Tiempo de riego {session.tipo_riego} expirado ({elapsed}s >= {duracion_seg}s) para asignación {session.id_asignacion}. Enviando comando de apagado."
            )

            try:
                stop_irrigation(db, pump_assignment or asig, "tiempo_maximo")
            except Exception:
                session_repository.rollback(db)
                logger.exception("Error apagando el relé por duración máxima")


_last_ml_scheduler_eval: dict[int, float] = {}

# Cotas del tiempo de espera dinamico que esta funcion sugiere al llamador
# (ver DEFAULT_ML_RECHECK_SECONDS mas abajo). Nunca se espera menos de esto
# aunque el cooldown de algun cultivo este a punto de cumplirse, ni mas de
# esto aunque todos los cultivos tengan cooldowns largos por delante.
MIN_ML_WAIT_SECONDS = 15
MAX_ML_WAIT_SECONDS = 300
# Cuando no hay ningun cultivo con cooldown pendiente (todos ya evaluados o
# ninguno elegible), o cuando la ultima evaluacion recomendo 'no_regar' y hay
# que reintentar pronto por si las lecturas de sensores cambian.
DEFAULT_ML_RECHECK_SECONDS = 60


def check_ml_cooldown_and_irrigate(db: Session) -> int:
    """
    Evalúa automáticamente los modelos ML para los cultivos activos cuando
    su período de cooldown entre riegos ya se ha cumplido. Si la predicción
    recomienda regar, inicia el riego y notifica vía WebSocket y MQTT.

    Devuelve cuántos segundos debería esperar el llamador antes de volver a
    invocar esta función: en vez de un intervalo fijo, se calcula en base al
    cooldown real configurado por cultivo (dinámico), tomando el menor tiempo
    restante entre todos los cultivos evaluados para no perder el momento en
    que el cooldown de cualquiera de ellos se cumple.
    """
    if not ml_eval_lock.acquire(blocking=False):
        # Otra evaluacion (scheduler/MQTT/manual) ya esta corriendo; esa
        # misma ve los datos actuales, no hace falta una segunda en paralelo.
        return MIN_ML_WAIT_SECONDS
    try:
        return _check_ml_cooldown_and_irrigate(db)
    finally:
        ml_eval_lock.release()


def _check_ml_cooldown_and_irrigate(db: Session) -> int:
    import time
    from src.main.model.models import cultivos
    from src.main.service.irrigationServ import (
        get_ml_cooldown_minutes,
        start_irrigation,
    )
    from src.main.service.mlServ import obtener_prediccion_riego
    from src.main.repositories import mqttRep as mqtt_rep
    from src.main.service.notifications.websocketManagerServ import broadcast_ws_event
    from src.main.service.notifications.alertEngineServ import notificar_riego_ejecutado_ml

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    current_time = time.time()
    next_wait_seconds = MAX_ML_WAIT_SECONDS

    all_crops = db.query(cultivos).all()
    for crop in all_crops:
        try:
            # 1. Buscar asignación de actuador activa para este cultivo
            pump_assignment = find_pump_assignment(db, crop.id_usuario, crop.id_cultivo)
            if not pump_assignment or not pump_assignment.activo:
                continue

            dev = pump_assignment.dispositivo
            if dev and not dev.funcionamiento_activo:
                continue

            # 1.1 El riego automático (IA) requiere que el usuario haya
            # configurado antes al menos un horario (de franja fija o
            # "siempre activo") para este actuador; si no, no se evalúa ni
            # se enciende nada automáticamente. Ademas, si el horario tiene
            # franja fija (no "siempre activo"), solo se evalua dentro de la
            # ventana hora_inicio-hora_fin configurada para ese dia.
            from src.main.service.horarioServ import horario_permite_ahora

            if not horario_permite_ahora(db, pump_assignment.id, now):
                continue

            # 2. Si hay un riego en curso o pausado a medio ciclo, no se evalua.
            if hay_riego_pendiente(db, pump_assignment):
                continue

            # 3. Verificar si el cooldown de riego ML ya se cumplió
            # Se usa pump_assignment.id_usuario (y no crop.id_usuario) porque
            # start_irrigation guarda la sesion con ese id_usuario; si no
            # coincidieran, la sesion recien creada quedaria invisible para
            # esta consulta y el cooldown nunca bloquearia nuevas evaluaciones.
            cooldown_minutos = get_ml_cooldown_minutes(
                db, pump_assignment.id_usuario, crop.id_cultivo
            )
            cooldown_segundos = cooldown_minutos * 60
            tiempo_cooldown = now - timedelta(minutes=cooldown_minutos)
            riego_reciente = mqtt_rep.queryProcesarMensajeRiegoReciente(
                db, crop.id_cultivo, pump_assignment.id_usuario, tiempo_cooldown
            )
            if riego_reciente:
                # Aún no cumple el tiempo de cooldown configurado. El proximo
                # chequeo util para ESTE cultivo es justo cuando se cumpla —
                # ni antes (desperdicia ciclos) ni despues (retrasa el riego).
                transcurrido = (now - riego_reciente.fecha_fin).total_seconds()
                restante = cooldown_segundos - transcurrido
                next_wait_seconds = min(next_wait_seconds, max(restante, MIN_ML_WAIT_SECONDS))
                continue

            # 4. El cooldown ya cumplió (pasaron >= cooldown_minutos desde el último riego).
            # Control de frecuencia: re-evaluar cada 15 segundos para no sobrecargar si recomienda 'no regar'.
            last_eval = _last_ml_scheduler_eval.get(crop.id_cultivo, 0.0)
            if current_time - last_eval < 15.0:
                next_wait_seconds = min(next_wait_seconds, MIN_ML_WAIT_SECONDS)
                continue
            _last_ml_scheduler_eval[crop.id_cultivo] = current_time

            # 5. Lecturas actuales de sensores (sin rellenar faltantes con 0.0)
            pred_input, motivo_sin_datos = leer_entradas_ml(db, crop.id_cultivo, now)
            if pred_input is None:
                logger.info(
                    f"[SCHEDULER ML] Cultivo {crop.id_cultivo}: no se evalua. {motivo_sin_datos}"
                )
                next_wait_seconds = min(next_wait_seconds, DEFAULT_ML_RECHECK_SECONDS)
                continue

            # 6. Ejecutar inferencia con el modelo ML activo
            resultado = obtener_prediccion_riego(
                data=pred_input,
                db=db,
                id_usuario=crop.id_usuario,
                id_cultivo=crop.id_cultivo,
                id_dispositivo=pump_assignment.id_dispositivo,
                persistir=True,
            )

            recomendacion = resultado.get("recomendacion")
            prob = resultado.get("probabilidad")
            logger.info(
                f"[SCHEDULER ML] Cooldown cumplido para cultivo {crop.id_cultivo} ({crop.nombre_planta}). "
                f"Predicción ML: {recomendacion} ({prob}%)"
            )

            # 7. Si la recomendación es regar, iniciar riego de inmediato
            if recomendacion == "regar":
                session = start_irrigation(
                    db=db,
                    assignment=pump_assignment,
                    irrigation_type="automatico_ml",
                    model_id=resultado.get("id_modelo"),
                    prediction_id=resultado.get("id_prediccion"),
                    now=now,
                )
                logger.info(f"[SCHEDULER ML] Riego automático iniciado exitosamente. Sesión={session.id}")
                broadcast_ws_event(
                    {
                        "tipo": "control_update",
                        "event": "riego_iniciado",
                        "id_cultivo": crop.id_cultivo,
                        "id_usuario": crop.id_usuario,
                    },
                    crop.id_usuario,
                )
                try:
                    notificar_riego_ejecutado_ml(
                        db=db,
                        id_usuario=crop.id_usuario,
                        id_cultivo=crop.id_cultivo,
                        datos_variables={
                            "humedad_suelo": pred_input.humedad_suelo,
                            "humedad_ambiente": pred_input.humedad_ambiente,
                            "temperatura_ambiente": pred_input.temperatura_ambiente,
                            "temperatura_suelo": pred_input.temperatura_suelo,
                        },
                        duracion_segundos=session.duracion_segundos,
                        nombre_cultivo=crop.nombre_planta,
                        id_asignacion=pump_assignment.id,
                    )
                except Exception as notif_err:
                    logger.warning(f"[SCHEDULER ML] Error notificando riego ML: {notif_err}")

                # Se acaba de iniciar un riego: el proximo chequeo util para
                # este cultivo es cuando termine su nuevo cooldown completo.
                next_wait_seconds = min(next_wait_seconds, cooldown_segundos)
            else:
                # 'no_regar': el cooldown ya esta cumplido, asi que hay que
                # reintentar pronto por si las lecturas de sensores cambian
                # (no esperar el cooldown completo de nuevo).
                next_wait_seconds = min(next_wait_seconds, DEFAULT_ML_RECHECK_SECONDS)

            # Notificar decisión de ML por WebSocket a la aplicación
            broadcast_ws_event(
                {
                    "tipo": "control_update",
                    "event": "ml_prediccion",
                    "id_cultivo": crop.id_cultivo,
                    "id_usuario": crop.id_usuario,
                },
                crop.id_usuario,
            )

        except Exception as crop_err:
            logger.warning(f"[SCHEDULER ML] Error evaluando ML para cultivo {crop.id_cultivo}: {crop_err}")

    return int(max(MIN_ML_WAIT_SECONDS, min(next_wait_seconds, MAX_ML_WAIT_SECONDS)))
