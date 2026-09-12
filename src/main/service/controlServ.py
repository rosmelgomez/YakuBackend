from src.main.core.devicePresence import device_is_connected
import os
from datetime import datetime, timezone
from typing import Any, List

from sqlalchemy.orm import Session

from src.main.model.models import (
    configuracion_control,
    cultivo_modelo,
    logs_sistema,
    programacion_riego,
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
        bomba_encendida = (
            config_t.bomba_encendida if config_t.bomba_encendida is not None else False
        )
        valvula_abierta = (
            config_t.valvula_abierta if config_t.valvula_abierta is not None else False
        )
        id_bomba = a.id
    else:
        pin_gpio = "N/A"
        estado_dispositivo = "offline"
        bomba_encendida = False
        valvula_abierta = False
        id_bomba = None

    es_conexion_directa = (tipo_fuente == "conexion_directa") or actuador_es_flujo

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
            id_usuario=userId, id_cultivo=idCultivo, id_modelo=id_mod, activo=False
        )
        session_repository.add(db, usr_mod)
        session_repository.commit(db)
        session_repository.refresh(db, usr_mod)

    tiene_modelo = usr_mod is not None
    predictivo_activo = (
        usr_mod.activo if (usr_mod and usr_mod.activo is not None) else False
    )

    if id_bomba:
        programaciones = data_repository.queryObtenerDatosControlProgramaciones(
            db, userId, id_bomba
        )
    else:
        programaciones = []

    programado_act = any(p.activo for p in programaciones)
    manual_act = not predictivo_activo and not programado_act

    modo_actual = "Manual"
    if predictivo_activo:
        modo_actual = "Predictivo (ML)"
    elif programado_act:
        modo_actual = "Programado"

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

    # 6. Horarios
    horarios = [
        {
            "id": p.id,
            "nombre": p.nombre if p.nombre else "Riego Programado",
            "hora": p.hora_inicio.strftime("%H:%M") if p.hora_inicio else "00:00",
            "dias": [
                p.lunes,
                p.martes,
                p.miercoles,
                p.jueves,
                p.viernes,
                p.sabado,
                p.domingo,
            ],
            "duracionMin": p.duracion_seg // 60 if p.duracion_seg is not None else 5,
            "activo": p.activo,
        }
        for p in programaciones
    ]

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
    if sesion_activa:
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
            "manualActivo": manual_act,
            "predictivoActivo": predictivo_activo,
            "programadoActivo": programado_act,
            "tieneModelo": tiene_modelo,
        },
        "cooldownMinutos": int(os.getenv("ML_IRRIGATION_COOLDOWN_MINUTES", "30")),
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


def establecer_modo_operacion(
    db: Session, userId: int, id_bomba: int, modo: str, idCultivo: int | None = None
) -> dict:
    modo = modo.lower()

    if idCultivo is None:
        asig = data_repository.queryEstablecerModoOperacionAsig(db, id_bomba)
        idCultivo = asig.id_cultivo if asig else None

    # Desactivar modelo si cambiamos a manual o programado
    if modo in ["manual", "programado"]:
        data_repository.queryEstablecerModoOperacionCultivoModelo(db, userId, idCultivo)

    # Desactivar programaciones si cambiamos a manual o predictivo
    if modo in ["manual", "predictivo"]:
        data_repository.queryEstablecerModoOperacionProgramacionRiego(
            db, userId, id_bomba
        )

    # Activar modelo si elegimos predictivo
    if modo == "predictivo":
        usr_mod = data_repository.queryEstablecerModoOperacionUsrMod(
            db, userId, idCultivo
        )
        if usr_mod:
            usr_mod.activo = True
        else:
            primer_modelo = data_repository.queryEstablecerModoOperacionPrimerModelo(db)
            id_mod = primer_modelo.id_modelo if primer_modelo else 1
            nuevo_usr_mod = cultivo_modelo(
                id_usuario=userId, id_cultivo=idCultivo, id_modelo=id_mod, activo=True
            )
            session_repository.add(db, nuevo_usr_mod)

        # EJECUTAR PREDICCIÓN ML EN VIVO DE INMEDIATO
        try:
            asig = data_repository.queryEstablecerModoOperacionAsig2(db, id_bomba)
            if asig and asig.activo:
                # Cargar las asignaciones de sensores (tipo 1) para este cultivo
                sensor_asigs = data_repository.queryEstablecerModoOperacionSensorAsigs(
                    db, idCultivo
                )
                sensor_asig_ids = [sa.id for sa in sensor_asigs]

                if sensor_asig_ids:
                    h_suelo = data_repository.queryEstablecerModoOperacionHSuelo(
                        db, sensor_asig_ids
                    )
                    h_amb = data_repository.queryEstablecerModoOperacionHAmb(
                        db, sensor_asig_ids
                    )
                    t_amb = data_repository.queryEstablecerModoOperacionTAmb(
                        db, sensor_asig_ids
                    )
                    t_suelo = data_repository.queryEstablecerModoOperacionTSuelo(
                        db, sensor_asig_ids
                    )

                    from src.main.dtos.mlDto import PrediccionRiegoModel

                    pred_input = PrediccionRiegoModel(
                        humedad_suelo=float(h_suelo.valor)
                        if h_suelo and h_suelo.valor is not None
                        else 0.0,
                        humedad_ambiente=float(h_amb.valor)
                        if h_amb and h_amb.valor is not None
                        else 0.0,
                        temperatura_ambiente=float(t_amb.temperatura)
                        if t_amb and t_amb.temperatura is not None
                        else 0.0,
                        temperatura_suelo=float(t_suelo.temperatura)
                        if t_suelo and t_suelo.temperatura is not None
                        else 0.0,
                    )

                    from src.main.service.mlServ import obtener_prediccion_riego

                    resultado = obtener_prediccion_riego(
                        data=pred_input,
                        db=db,
                        id_usuario=userId,
                        id_cultivo=idCultivo,
                        id_dispositivo=asig.id_dispositivo,
                    )

                    # Si la recomendación es regar, iniciar el riego
                    if resultado.get("recomendacion") == "regar":
                        from src.main.service.irrigationServ import start_irrigation

                        start_irrigation(
                            db=db,
                            assignment=asig,
                            irrigation_type="automatico_ml",
                            model_id=resultado.get("id_modelo"),
                            prediction_id=resultado.get("id_prediccion"),
                        )
        except Exception as e:
            pass

    # Activar programaciones si elegimos programado
    if modo == "programado":
        data_repository.queryEstablecerModoOperacionProgramacionRiego2(
            db, userId, id_bomba
        )

    # Auditoría
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion=f"Cambio de modo a {modo}",
        modulo="Control y Configuración",
        descripcion=f"El usuario cambió el modo de operación de riego a {modo}.",
    )
    session_repository.add(db, nuevo_log)
    session_repository.commit(db)

    # Enviar comando MQTT al ESP32
    asig = data_repository.queryEstablecerModoOperacionAsig3(db, id_bomba)
    if asig:
        try:
            import json

            payload = json.dumps({"accion": "CAMBIO_MODO", "modo": modo})
            _publish_relay_command(asig, payload)
        except Exception as mqtt_err:
            pass

    return {"status": "ok", "message": f"Modo de operación cambiado a {modo}."}


def conmutar_bomba_manual(
    db: Session, userId: int, idBomba: int, encender: bool
) -> dict:
    asig = data_repository.queryConmutarBombaManualAsig(db, idBomba)
    if not asig or asig.id_usuario != userId:
        raise ValueError("Asignacion de bomba no encontrada.")

    cultivo = asig.cultivo
    fuente = cultivo.fuente_agua if cultivo else None
    dev = asig.dispositivo
    es_directa = False
    if fuente and fuente.tipo:
        try:
            es_directa = normalize_source_type(fuente.tipo) == "conexion_directa"
        except Exception:
            es_directa = str(fuente.tipo).lower() == "conexion_directa"
    if not es_directa and dev:
        metodo = getattr(dev, "metodo_medicion", None) or (dev.tipo and getattr(dev.tipo, "metodo_medicion", None))
        es_directa = (metodo == "flujometro")

    nombre_actuador = "Válvula de riego" if es_directa else "Bomba"

    if encender:
        session = start_irrigation(db, asig, "manual")
        timeout_min = max((session.duracion_segundos or 0) // 60, MIN_RELAY_MINUTES)
    else:
        stop_irrigation(db, asig, "apagado_manual")
        timeout_min = get_max_relay_seconds(db, userId, asig.id_cultivo) // 60

    # 4. Auditoría
    accion_str = f"Encendido manual de {nombre_actuador.lower()}" if encender else f"Apagado manual de {nombre_actuador.lower()}"
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion=accion_str,
        modulo="Control y Configuración",
        descripcion=f"El usuario forzó el estado de {nombre_actuador.lower()} a {'ON' if encender else 'OFF'}.",
    )
    session_repository.add(db, nuevo_log)
    session_repository.commit(db)
    return {
        "status": "ok",
        "message": f"{nombre_actuador} conmutada a {'ON' if encender else 'OFF'}.",
        "timeoutMin": timeout_min,
    }


def conmutar_valvula_manual(
    db: Session, userId: int, idBomba: int, abrir: bool
) -> dict:
    asig = data_repository.queryConmutarValvulaManualAsig(db, idBomba)
    if not asig or asig.id_usuario != userId:
        raise ValueError("Asignacion de actuador no encontrada.")

    config = data_repository.queryConmutarValvulaManualConfig(db, asig)
    if not config:
        raise ValueError("Configuracion de tanque no encontrada.")

    config.valvula_abierta = abrir
    session_repository.add(db, config)
    _publish_relay_command(asig, build_valve_command(abrir))

    accion_str = "Apertura manual de valvula" if abrir else "Cierre manual de valvula"
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion=accion_str,
        modulo="Control y Configuracion",
        descripcion=f"El usuario forzo el estado de la valvula a {'ON' if abrir else 'OFF'}.",
    )
    session_repository.add(db, nuevo_log)
    session_repository.commit(db)
    return {
        "status": "ok",
        "message": f"Valvula conmutada a {'ON' if abrir else 'OFF'}.",
    }


def actualizar_tiempo_maximo_rele(
    db: Session, userId: int, idCultivo: int, duracionMin: int
) -> dict:
    if not MIN_RELAY_MINUTES <= duracionMin <= MAX_RELAY_MINUTES:
        raise ValueError(
            f"La duracion debe estar entre {MIN_RELAY_MINUTES} y {MAX_RELAY_MINUTES} minutos."
        )

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


def crear_horario_riego(
    db: Session,
    userId: int,
    idBomba: int,
    hora: str,
    duracionMin: int,
    dias: List[bool],
    nombre: str | None = None,
) -> dict:
    h_str, m_str = hora.split(":")
    h = int(h_str)
    m = int(m_str)

    fecha_ini = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)

    if duracionMin < MIN_RELAY_MINUTES or duracionMin > MAX_RELAY_MINUTES:
        raise ValueError(
            f"La duracion del horario debe estar entre {MIN_RELAY_MINUTES} y {MAX_RELAY_MINUTES} minutos."
        )

    # Resolver id_cultivo desde la asignación del actuador/bomba
    asig = data_repository.queryCrearHorarioRiegoAsig(db, idBomba)
    id_cultivo = asig.id_cultivo if asig else None

    nuevo_horario = programacion_riego(
        id_usuario=userId,
        id_asignacion=idBomba,
        id_cultivo=id_cultivo,
        nombre=nombre,
        hora_inicio=fecha_ini,
        duracion_seg=duracionMin * 60,
        activo=True,
        lunes=dias[0],
        martes=dias[1],
        miercoles=dias[2],
        jueves=dias[3],
        viernes=dias[4],
        sabado=dias[5],
        domingo=dias[6],
    )
    session_repository.add(db, nuevo_horario)

    # Auditoría
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion="Creación de horario de riego",
        modulo="Control y Configuración",
        descripcion=f"Se creó una programación de riego llamada '{nombre or 'Sin nombre'}' a las {hora} por {duracionMin} minutos.",
    )
    session_repository.add(db, nuevo_log)
    session_repository.commit(db)
    return {"status": "ok", "message": "Horario agregado con éxito."}


def actualizar_horario_riego(
    db: Session,
    userId: int,
    id_horario: int,
    hora: str,
    duracionMin: int,
    dias: List[bool],
    nombre: str | None = None,
) -> dict | None:
    horario = data_repository.queryActualizarHorarioRiegoHorario(db, id_horario, userId)

    if not horario:
        return None

    h_str, m_str = hora.split(":")
    h = int(h_str)
    m = int(m_str)
    fecha_ini = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)

    if duracionMin < MIN_RELAY_MINUTES or duracionMin > MAX_RELAY_MINUTES:
        raise ValueError(
            f"La duracion del horario debe estar entre {MIN_RELAY_MINUTES} y {MAX_RELAY_MINUTES} minutos."
        )

    horario.nombre = nombre
    horario.hora_inicio = fecha_ini
    horario.duracion_seg = duracionMin * 60
    horario.lunes = dias[0]
    horario.martes = dias[1]
    horario.miercoles = dias[2]
    horario.jueves = dias[3]
    horario.viernes = dias[4]
    horario.sabado = dias[5]
    horario.domingo = dias[6]

    session_repository.add(db, horario)

    # Auditoría
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion="Actualización de horario de riego",
        modulo="Control y Configuración",
        descripcion=f"Se actualizó la programación de riego ID {id_horario} llamada '{nombre or 'Sin nombre'}' a las {hora} por {duracionMin} minutos.",
    )
    session_repository.add(db, nuevo_log)
    session_repository.commit(db)
    return {"status": "ok", "message": "Horario actualizado con éxito."}


def conmutar_horario_riego(
    db: Session, userId: int, id_horario: int, activo: bool
) -> dict | None:
    horario = data_repository.queryConmutarHorarioRiegoHorario(db, id_horario, userId)

    if not horario:
        return None

    horario.activo = activo
    session_repository.add(db, horario)

    # Auditoría
    accion_str = (
        "Activación de horario de riego"
        if activo
        else "Desactivación de horario de riego"
    )
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion=accion_str,
        modulo="Control y Configuración",
        descripcion=f"Se {'activó' if activo else 'desactivó'} el horario de riego ID: {id_horario}.",
    )
    session_repository.add(db, nuevo_log)
    session_repository.commit(db)
    return {
        "status": "ok",
        "message": f"Horario {'activado' if activo else 'desactivado'}.",
    }


def eliminar_horario_riego(db: Session, userId: int, id_horario: int) -> dict | None:
    horario = data_repository.queryEliminarHorarioRiegoHorario(db, id_horario, userId)

    if not horario:
        return None

    session_repository.delete(db, horario)

    # Auditoría
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion="Eliminación de horario de riego",
        modulo="Control y Configuración",
        descripcion=f"Se eliminó el horario de riego ID: {id_horario}.",
    )
    session_repository.add(db, nuevo_log)
    session_repository.commit(db)
    return {"status": "ok", "message": "Horario eliminado."}


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
