from src.main.core.devicePresence import device_is_connected
import os
from datetime import datetime, timezone
from typing import Any, List

from sqlalchemy.orm import Session

from src.main.model.models import (
    configuracion_control,
    cultivo_modelo,
    logs_sistema,
)
from src.main.repositories import controlRep as data_repository
from src.main.repositories import sessionRep as session_repository
from src.main.service.dashboardServ import _get_timezone, _to_timezone, _to_timezone_iso
from src.main.core.waterSource import normalize_source_type
from src.main.service.irrigationServ import (
    MAX_RELAY_MINUTES,
    MIN_RELAY_MINUTES,
    _publish_relay_command,
    build_valve_command,
    get_max_relay_seconds,
    start_irrigation,
    stop_irrigation,
)


def obtener_datos_control(
    db: Session, userId: int, idCultivo: int, user_rol_id: int
) -> dict:

    usuario = data_repository.queryObtenerDatosControlUsuario(db, userId)
    user_tz = _get_timezone(usuario.zona_horaria if usuario else None)
    # 1. Validar roles
    rol = data_repository.queryObtenerDatosControlRol(db, user_rol_id)
    rol_nombre = rol.nombre.lower() if rol else ""
    esInvestigador = "investigador" in rol_nombre
    esAdmin = "admin" in rol_nombre or "administrador" in rol_nombre

    # 2. Obtener todas las asignaciones vinculadas al cultivo
    asigs = data_repository.queryObtenerDatosControlAsigs(db, userId, idCultivo)

    bomba_asig = None
    for a in asigs:
        config_t = data_repository.queryObtenerDatosControlConfigT(db, a)
        if config_t is not None:
            bomba_asig = (a, config_t)
            break

    cultivo = data_repository.queryObtenerDatosControlCultivo(db, idCultivo)
    fuente_agua = cultivo.fuente_agua if cultivo else None
    tipo_fuente = "tanque"
    if fuente_agua and fuente_agua.tipo:
        try:
            tipo_fuente = normalize_source_type(fuente_agua.tipo)
        except Exception:
            tipo_fuente = str(fuente_agua.tipo).lower()

    actuador_es_flujo = False
    actuador_tipo_nombre = None
    actuador_metodo = None

    if bomba_asig:
        a, config_t = bomba_asig
        dev = data_repository.queryObtenerDatosControlDev(db, a)
        pin_gpio = a.pin_gpio if a.pin_gpio is not None else "N/A"
        estado_dispositivo = dev.estado if dev else "offline"
        if dev:
            actuador_metodo = getattr(dev, "metodo_medicion", None)
            if dev.tipo:
                actuador_tipo_nombre = dev.tipo.nombre
                if not actuador_metodo:
                    actuador_metodo = getattr(dev.tipo, "metodo_medicion", None)
            if actuador_metodo == "flujometro":
                actuador_es_flujo = True
        actuador_activo = bool(a.activo)
        bomba_encendida = (
            (config_t.bomba_encendida if config_t.bomba_encendida is not None else False)
            if actuador_activo
            else False
        )
        valvula_abierta = (
            (config_t.valvula_abierta if config_t.valvula_abierta is not None else False)
            if actuador_activo
            else False
        )
        id_bomba = a.id
    else:
        actuador_activo = False
        pin_gpio = "N/A"
        estado_dispositivo = "offline"
        bomba_encendida = False
        valvula_abierta = False
        id_bomba = None

    es_conexion_directa = (tipo_fuente == "conexion_directa") or actuador_es_flujo
    if es_conexion_directa:
        valvula_abierta = valvula_abierta or bomba_encendida
        bomba_encendida = valvula_abierta

    # 3. Timeout config
    config_c = data_repository.queryObtenerDatosControlConfigC(db, userId, idCultivo)
    timeout_min = get_max_relay_seconds(db, userId, idCultivo) // 60

    # 4. Modo de operación
    usr_mod = data_repository.queryObtenerDatosControlUsrMod(db, userId, idCultivo)

    if not usr_mod:
        default_model = data_repository.queryObtenerDatosControlDefaultModel(db)
        if not default_model:
            default_model = data_repository.queryObtenerDatosControlDefaultModel2(db)
        id_mod = default_model.id_modelo if default_model else 1
        usr_mod = cultivo_modelo(
            id_usuario=userId, id_cultivo=idCultivo, id_modelo=id_mod, activo=True
        )
        session_repository.add(db, usr_mod)
        session_repository.commit(db)
        session_repository.refresh(db, usr_mod)
    elif not usr_mod.activo:
        usr_mod.activo = True
        session_repository.add(db, usr_mod)
        session_repository.commit(db)

    tiene_modelo = True
    predictivo_activo = True
    modo_actual = "Predictivo (ML)"

    # 5. Logs de auditoría
    sys_logs = data_repository.queryObtenerDatosControlSysLogs(db, userId)

    logs_unificados = [
        {
            "id": str(l.id),
            "fecha": _to_timezone(l.fecha, user_tz).strftime("%Y-%m-%d %H:%M:%S")
            if l.fecha
            else "",
            "modulo": l.modulo if l.modulo else "General",
            "accion": l.accion,
            "descripcion": l.descripcion if l.descripcion else "-",
            "ip_acceso": l.ip_acceso if l.ip_acceso else "N/A",
        }
        for l in sys_logs
    ]

    # 6. Horarios (Modos manual y programado eliminados; ML es el único modo)
    horarios = []


    # 6b. Última predicción de ML
    ultima_pred = data_repository.queryObtenerDatosControlUltimaPred(
        db, userId, idCultivo
    )

    if ultima_pred:
        modelo = data_repository.queryObtenerDatosControlModelo(db, ultima_pred)
        nombre_modelo = modelo.nombre_modelo if modelo else "Modelo Desconocido"
        pred_dict = {
            "recomendacion": ultima_pred.recomendacion,
            "probabilidad": float(ultima_pred.probabilidad)
            if ultima_pred.probabilidad is not None
            else None,
            "fecha": _to_timezone(ultima_pred.fecha, user_tz).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            if ultima_pred.fecha
            else "",
            "variables": ultima_pred.variables_entrada,
            "nombre_modelo": nombre_modelo,
        }
    else:
        pred_dict = None

    # 6c. Tiempo desde el último riego y estado de pausa
    ultima_sesion = data_repository.queryObtenerDatosControlUltimaSesion(
        db, userId, idCultivo
    )

    tiempo_desde_ultimo_riego_seg = None
    ultimo_riego_fecha_fin = None
    if ultima_sesion:
        fecha_fin = ultima_sesion.fecha_fin or ultima_sesion.fecha
        ahora_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        tiempo_desde_ultimo_riego_seg = max(
            0, int((ahora_naive - fecha_fin).total_seconds())
        )
        ultimo_riego_fecha_fin = _to_timezone_iso(fecha_fin, user_tz)

    # Buscar sesión actualmente pausada
    sesion_pausada = data_repository.queryObtenerDatosControlSesionPausada(db, id_bomba)

    es_pausado = False
    pausado_tiempo_restante = 0
    pausado_tiempo_transcurrido = 0
    pausado_duracion_segundos = 0
    pausado_motivo = None
    if sesion_pausada:
        es_pausado = True
        pausado_duracion_segundos = int(sesion_pausada.duracion_segundos or 0)
        pausado_tiempo_transcurrido = int(sesion_pausada.segundos_acumulados or 0)
        motivo_str = sesion_pausada.motivo_cierre
        if motivo_str.startswith("pausado_"):
            content = motivo_str[len("pausado_") :]
            rparts = content.rsplit("_", 1)
            if len(rparts) == 2:
                pausado_motivo = rparts[0]
                try:
                    elapsed = int(rparts[1])
                except ValueError:
                    elapsed = pausado_tiempo_transcurrido
                pausado_tiempo_transcurrido = max(pausado_tiempo_transcurrido, elapsed)
                pausado_tiempo_restante = max(
                    0, pausado_duracion_segundos - pausado_tiempo_transcurrido
                )
            else:
                pausado_motivo = content
                pausado_tiempo_restante = max(
                    0, pausado_duracion_segundos - pausado_tiempo_transcurrido
                )
        else:
            pausado_motivo = "sin_agua"
            pausado_tiempo_restante = max(
                0, pausado_duracion_segundos - pausado_tiempo_transcurrido
            )

    # Buscar sesión de riego activa
    sesion_activa = data_repository.queryObtenerDatosControlSesionActiva(db, id_bomba)

    riego_activo_payload = None
    if sesion_activa and actuador_activo:
        from src.main.service.irrigationServ import executed_seconds

        now_ref = datetime.now(timezone.utc).replace(tzinfo=None)
        elapsed_sec = executed_seconds(sesion_activa, now_ref)
        riego_activo_payload = {
            "id": sesion_activa.id,
            "segundosTranscurridos": elapsed_sec,
            "duracionSegundos": sesion_activa.duracion_segundos,
            "fechaInicio": _to_timezone_iso(sesion_activa.fecha_inicio, user_tz),
            "fechaReferencia": now_ref.isoformat() + "Z",
        }
        bomba_encendida = True
        if es_conexion_directa:
            valvula_abierta = True
    elif (bomba_encendida or valvula_abierta) and actuador_activo:
        now_ref = datetime.now(timezone.utc).replace(tzinfo=None)
        riego_activo_payload = {
            "id": 0,
            "segundosTranscurridos": 0,
            "duracionSegundos": timeout_min * 60,
            "fechaInicio": _to_timezone_iso(now_ref, user_tz),
            "fechaReferencia": now_ref.isoformat() + "Z",
        }

    if not actuador_activo:
        es_pausado = False
        riego_activo_payload = None

    # 7. Mapear dispositivos asociados a este cultivo
    dispositivos_map = {}
    for a in asigs:
        dev = data_repository.queryObtenerDatosControlDev2(db, a)
        if dev and dev.id_dispositivo not in dispositivos_map:
            tipo = data_repository.queryObtenerDatosControlTipo(db, dev)
            tipo_nombre = tipo.nombre if tipo else ""

            # Buscar componentes asignados
            componentes_asig = []
            for a2 in asigs:
                if (
                    a2.id_dispositivo == dev.id_dispositivo
                    and a2.id_componente is not None
                ):
                    comp = data_repository.queryObtenerDatosControlComp(db, a2)
                    if comp:
                        tipo_comp = data_repository.queryObtenerDatosControlTipoComp(
                            db, comp
                        )
                        componentes_asig.append(
                            {
                                "id": comp.id,
                                "nombre": tipo_comp.nombre_modelo
                                if tipo_comp
                                else "Desconocido",
                                "categoria": tipo_comp.categoria if tipo_comp else "",
                                "pin": a2.pin_gpio
                                if a2.pin_gpio is not None
                                else "N/A",
                                "offsetCalibracion": float(a2.offset_calibracion)
                                if a2.offset_calibracion is not None
                                else 0.0,
                            }
                        )

            funcionamiento_activo = any(
                a2.activo for a2 in asigs if a2.id_dispositivo == dev.id_dispositivo
            )

            dispositivos_map[dev.id_dispositivo] = {
                "id": dev.id_dispositivo,
                "nombre": dev.nombre,
                "mac": dev.mac_address if dev.mac_address else "N/A",
                "funcionamientoActivo": funcionamiento_activo,
                "conectado": device_is_connected(dev.ultimo_ping, timeout_seconds=int(os.getenv("DEVICE_OFFLINE_TIMEOUT_SECONDS", "130"))),
                "ultimo_ping": dev.ultimo_ping,
                "estado": dev.estado if dev.estado else "offline",
                "tipoId": dev.id_tipo,
                "tipoNombre": tipo_nombre,
                "sensores": componentes_asig,
            }

    return {
        "bomba": {
            "id": id_bomba,
            "pin": pin_gpio,
            "online": estado_dispositivo == "activo",
            "encendida": bomba_encendida,
            "timeoutMin": timeout_min,
        },
        "valvula": {
            "id": id_bomba,
            "pin": 25,
            "abierta": valvula_abierta,
            "modoAuto": True,
        },
        "seguridad": {"esInvestigador": esInvestigador, "esAdmin": esAdmin},
        "modo": {
            "actual": modo_actual,
            "predictivoActivo": True,
            "tieneModelo": True,
        },
        "cooldownMinutos": (
            config_c.cooldown_minutos
            if (config_c and getattr(config_c, "cooldown_minutos", None) is not None)
            else int(os.getenv("ML_IRRIGATION_COOLDOWN_MINUTES", "30"))
        ),
        "tiempoDesdeUltimoRiegoSeg": tiempo_desde_ultimo_riego_seg,
        "ultimoRiegoFechaFin": ultimo_riego_fecha_fin,
        "esConexionDirecta": es_conexion_directa,
        "fuenteAgua": {
            "id": fuente_agua.id if fuente_agua else None,
            "nombre": fuente_agua.nombre if fuente_agua else None,
            "tipo": tipo_fuente,
        } if fuente_agua else None,
        "actuadorTipo": {
            "metodoMedicion": actuador_metodo,
            "tipoNombre": actuador_tipo_nombre,
        },
        "sesionPausada": {
            "activa": es_pausado,
            "motivo": pausado_motivo,
            "segundosTranscurridos": pausado_tiempo_transcurrido,
            "duracionSegundos": pausado_duracion_segundos,
            "tiempoRestanteSeg": pausado_tiempo_restante,
        },
        "logs": logs_unificados,
        "horarios": horarios,
        "dispositivos": list(dispositivos_map.values()),
        "ultimaPrediccion": pred_dict,
        "riegoActivo": riego_activo_payload,
    }


def actualizar_tiempo_maximo_rele(
    db: Session, userId: int, idCultivo: int, duracionMin: int
) -> dict:
    if not MIN_RELAY_MINUTES <= duracionMin <= MAX_RELAY_MINUTES:
        raise ValueError(
            f"La duracion debe estar entre {MIN_RELAY_MINUTES} y {MAX_RELAY_MINUTES} minutos."
        )

    try:
        from src.main.service.irrigationServ import find_pump_assignment
        asig = find_pump_assignment(db, userId, idCultivo)
        if asig:
            sesion_activa = data_repository.queryObtenerDatosControlSesionActiva(db, asig.id)
            config_t = data_repository.queryObtenerDatosControlConfigT(db, asig)
            if sesion_activa or (config_t and config_t.bomba_encendida):
                raise ValueError(
                    "Bloqueado: no se puede modificar el tiempo de riego mientras el actuador está en funcionamiento."
                )
    except ValueError:
        raise
    except Exception:
        pass

    config = data_repository.queryActualizarTiempoMaximoReleConfig(
        db, userId, idCultivo
    )
    if config is None:
        config = configuracion_control(
            id_usuario=userId,
            id_cultivo=idCultivo,
            duracion_riego_max_seg=duracionMin * 60,
        )
    else:
        config.duracion_riego_max_seg = duracionMin * 60
        config.actualizado_en = datetime.now()
    session_repository.add(db, config)
    session_repository.add(
        db,
        logs_sistema(
            id_usuario=userId,
            accion="Actualizacion de tiempo maximo del rele",
            modulo="Control y Configuracion",
            descripcion=f"Tiempo maximo del rele actualizado a {duracionMin} minutos para el cultivo {idCultivo}.",
        ),
    )
    session_repository.commit(db)
    return {"status": "ok", "duracionMaxMinutos": duracionMin}


def actualizar_cooldown_riego(
    db: Session, userId: int, idCultivo: int, cooldownMinutos: int
) -> dict:
    if not 1 <= cooldownMinutos <= 1440:
        raise ValueError("El tiempo de cooldown debe estar entre 1 y 1440 minutos.")

    try:
        from src.main.service.irrigationServ import find_pump_assignment
        asig = find_pump_assignment(db, userId, idCultivo)
        if asig:
            sesion_activa = data_repository.queryObtenerDatosControlSesionActiva(db, asig.id)
            config_t = data_repository.queryObtenerDatosControlConfigT(db, asig)
            if sesion_activa or (config_t and config_t.bomba_encendida):
                raise ValueError(
                    "Bloqueado: no se puede modificar el tiempo de cooldown mientras el riego está en curso."
                )
    except ValueError:
        raise
    except Exception:
        pass

    config = data_repository.queryActualizarTiempoMaximoReleConfig(
        db, userId, idCultivo
    )
    if config is None:
        config = configuracion_control(
            id_usuario=userId,
            id_cultivo=idCultivo,
            duracion_riego_max_seg=600,
            cooldown_minutos=cooldownMinutos,
        )
    else:
        config.cooldown_minutos = cooldownMinutos
        config.actualizado_en = datetime.now()
    session_repository.add(db, config)
    session_repository.add(
        db,
        logs_sistema(
            id_usuario=userId,
            accion="Actualizacion de cooldown de riego ML",
            modulo="Control y Configuracion",
            descripcion=f"Tiempo de cooldown ML actualizado a {cooldownMinutos} minutos para el cultivo {idCultivo}.",
        ),
    )
    session_repository.commit(db)

    # Si el tiempo transcurrido desde el último riego ya cumplió el nuevo cooldown y el actuador está activo,
    # evaluar inmediatamente el modelo ML para iniciar el riego si se requiere
    try:
        from src.main.service.schedulerServ import check_ml_cooldown_and_irrigate, _last_ml_scheduler_eval
        _last_ml_scheduler_eval[idCultivo] = 0.0
        check_ml_cooldown_and_irrigate(db)
    except Exception as eval_err:
        logger.warning(f"Error evaluando ML inmediatamente tras actualizar cooldown: {eval_err}")

    return {"status": "ok", "cooldownMinutos": cooldownMinutos}





def conmutar_bomba_por_telemetria(
    db: Session, userId: int, id_telemetria: int, estado: bool
) -> dict | None:
    # 1. Actualizar telemetria_tanque
    telemetria = data_repository.queryConmutarBombaPorTelemetriaTelemetria(
        db, id_telemetria
    )
    if not telemetria:
        return None

    telemetria.bomba_encendida = estado
    session_repository.add(db, telemetria)

    # 2. Obtener asignación para conocer el cultivo y bomba
    asig = data_repository.queryConmutarBombaPorTelemetriaAsig(db, telemetria)
    pump_assignment = None
    if asig:
        pump_assignment = data_repository.queryConmutarBombaPorTelemetriaPumpAssignment(
            db, userId, asig
        )
    if pump_assignment:
        if estado:
            start_irrigation(db, pump_assignment, "manual")
        else:
            stop_irrigation(db, pump_assignment, "apagado_manual")

    # 3. Auditoría
    accion_str = "Encendido manual de bomba" if estado else "Apagado manual de bomba"
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion=accion_str,
        modulo="Dashboard Principal",
        descripcion=f"Actualización de bomba desde widget de Tanque (Telemetría ID: {id_telemetria})",
    )
    session_repository.add(db, nuevo_log)
    session_repository.commit(db)
    return {
        "status": "ok",
        "message": f"Bomba conmutada a {'ON' if estado else 'OFF'}.",
    }


def actualizar_umbrales_riego(
    db: Session, userId: int, id_cultivo: int, updates: List[Any]
) -> dict:
    for u in updates:
        data_repository.queryActualizarUmbralesRiegoConfiguracionUmbrales(
            db, u, userId, id_cultivo
        )
    session_repository.commit(db)
    return {"status": "ok", "message": "Umbrales actualizados con éxito."}


def detener_riego_cultivo(
    db: Session, userId: int, idCultivo: int, motivo: str = "cronometro_completado"
) -> dict:
    from src.main.service.irrigationServ import find_pump_assignment, stop_irrigation
    from src.main.service.mqttServ import broadcast_ws_event

    pump_assignment = find_pump_assignment(db, userId, idCultivo)
    if not pump_assignment:
        raise HTTPException(
            status_code=404, detail="No se encontró actuador activo para este cultivo."
        )

    session = stop_irrigation(db, pump_assignment, motivo, publish=True)

    # Al detenerse la válvula, por defecto el sensor de flujo deja de capturar datos
    flow_asigs = (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id_cultivo == idCultivo)
        .all()
    )
    for a in flow_asigs:
        dev = a.dispositivo
        if dev and (dev.metodo_medicion == "flujometro" or (dev.tipo and getattr(dev.tipo, "categoria", None) == "sensor")):
            a.activo = False
            session_repository.add(db, a)
            try:
                from src.main.tasks.mqttSubscriberTask import publish_mqtt_message
                topic = f"yaku/dispositivo/{dev.client_id_mqtt}/config"
                publish_mqtt_message(topic, json.dumps({"funcionamiento_activo": False}), qos=1, retain=True)
            except Exception as mq_err:
                logger.warning(f"No se pudo notificar desactivacion a sensor via MQTT: {mq_err}")

    broadcast_ws_event(
        {
            "tipo": "control_update",
            "event": "riego_detenido",
            "id_cultivo": idCultivo,
            "id_usuario": userId,
            "motivo": motivo,
        },
        userId,
    )
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion="Detencion de riego por cronometro",
        modulo="Control y Configuracion",
        descripcion=f"Riego detenido ({motivo}) y comando MQTT OFF enviado para cultivo {idCultivo}.",
    )
    session_repository.add(db, nuevo_log)
    session_repository.commit(db)
    return {
        "status": "ok",
        "message": f"Riego detenido exitosamente ({motivo}). Comando MQTT OFF enviado.",
    }
