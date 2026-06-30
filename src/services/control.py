import os
from datetime import datetime, timezone
from typing import List, Any
from sqlalchemy.orm import Session

from ..db.models import (
    roles,
    asignaciones_iot,
    configuracion_tanque,
    dispositivos,
    configuracion_control,
    cultivo_modelo,
    programacion_riego,
    logs_sistema,
    tipos_dispositivo,
    componentes,
    tipos_componente,
    telemetria_tanque,
    configuracion_umbrales,
    modelos_ml
)
from .irrigation import (
    MAX_RELAY_MINUTES,
    MIN_RELAY_MINUTES,
    build_valve_command,
    get_max_relay_seconds,
    start_irrigation,
    stop_irrigation,
    _publish_relay_command,
)


def obtener_datos_control(db: Session, userId: int, idCultivo: int, user_rol_id: int) -> dict:
    # 1. Validar roles
    rol = db.query(roles).filter(roles.id_rol == user_rol_id).first()
    rol_nombre = rol.nombre.lower() if rol else ""
    esInvestigador = "investigador" in rol_nombre
    esAdmin = "admin" in rol_nombre or "administrador" in rol_nombre
    
    # 2. Obtener todas las asignaciones vinculadas al cultivo
    asigs = db.query(asignaciones_iot).filter(
        asignaciones_iot.id_usuario == userId,
        asignaciones_iot.id_cultivo == idCultivo
    ).all()
    
    bomba_asig = None
    for a in asigs:
        config_t = db.query(configuracion_tanque).filter(configuracion_tanque.id_asignacion == a.id).first()
        if config_t is not None:
            bomba_asig = (a, config_t)
            break
            
    if bomba_asig:
        a, config_t = bomba_asig
        dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == a.id_dispositivo).first()
        pin_gpio = a.pin_gpio if a.pin_gpio is not None else "N/A"
        estado_dispositivo = dev.estado if dev else "offline"
        bomba_encendida = config_t.bomba_encendida if config_t.bomba_encendida is not None else False
        valvula_abierta = config_t.valvula_abierta if config_t.valvula_abierta is not None else False
        id_bomba = a.id
    else:
        pin_gpio = "N/A"
        estado_dispositivo = "offline"
        bomba_encendida = False
        valvula_abierta = False
        id_bomba = None
        
    # 3. Timeout config
    config_c = db.query(configuracion_control).filter(
        configuracion_control.id_usuario == userId,
        configuracion_control.id_cultivo == idCultivo
    ).first()
    timeout_min = get_max_relay_seconds(db, userId, idCultivo) // 60
    
    # 4. Modo de operación
    usr_mod = db.query(cultivo_modelo).filter(
        cultivo_modelo.id_usuario == userId,
        cultivo_modelo.id_cultivo == idCultivo
    ).order_by(cultivo_modelo.fecha_asignacion.desc()).first()
    
    if not usr_mod:
        default_model = db.query(modelos_ml).filter(modelos_ml.es_default == True).first()
        if not default_model:
            default_model = db.query(modelos_ml).order_by(modelos_ml.id_modelo.asc()).first()
        id_mod = default_model.id_modelo if default_model else 1
        usr_mod = cultivo_modelo(
            id_usuario=userId,
            id_cultivo=idCultivo,
            id_modelo=id_mod,
            activo=False
        )
        db.add(usr_mod)
        db.commit()
        db.refresh(usr_mod)
        
    tiene_modelo = usr_mod is not None
    predictivo_activo = usr_mod.activo if (usr_mod and usr_mod.activo is not None) else False
    
    if id_bomba:
        programaciones = db.query(programacion_riego).filter(
            programacion_riego.id_usuario == userId,
            programacion_riego.id_asignacion == id_bomba
        ).order_by(programacion_riego.hora_inicio.asc()).all()
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
    sys_logs = db.query(logs_sistema).filter(
        logs_sistema.id_usuario == userId
    ).order_by(logs_sistema.fecha.desc()).limit(20).all()
    
    logs_unificados = [
        {
            "id": str(l.id),
            "fecha": l.fecha.strftime("%Y-%m-%d %H:%M:%S") if l.fecha else "",
            "modulo": l.modulo if l.modulo else "General",
            "accion": l.accion,
            "descripcion": l.descripcion if l.descripcion else "-",
            "ip_acceso": l.ip_acceso if l.ip_acceso else "N/A"
        }
        for l in sys_logs
    ]
    
    # 6. Horarios
    horarios = [
        {
            "id": p.id,
            "nombre": p.nombre if p.nombre else "Riego Programado",
            "hora": p.hora_inicio.strftime("%H:%M") if p.hora_inicio else "00:00",
            "dias": [p.lunes, p.martes, p.miercoles, p.jueves, p.viernes, p.sabado, p.domingo],
            "duracionMin": p.duracion_seg // 60 if p.duracion_seg is not None else 5,
            "activo": p.activo
        }
        for p in programaciones
    ]
    
    # 6b. Última predicción de ML
    from ..db.models import predicciones_ml
    ultima_pred = db.query(predicciones_ml).filter(
        predicciones_ml.id_usuario == userId,
        predicciones_ml.id_cultivo == idCultivo
    ).order_by(predicciones_ml.fecha.desc()).first()
    
    if ultima_pred:
        pred_dict = {
            "recomendacion": ultima_pred.recomendacion,
            "probabilidad": float(ultima_pred.probabilidad) if ultima_pred.probabilidad is not None else None,
            "fecha": (ultima_pred.fecha.strftime("%Y-%m-%d %H:%M:%S") + " UTC") if ultima_pred.fecha else "",
            "variables": ultima_pred.variables_entrada
        }
    else:
        pred_dict = None
        
    # 6c. Tiempo desde el último riego y estado de pausa
    from ..db.models import riego
    ultima_sesion = db.query(riego).join(
        asignaciones_iot,
        riego.id_asignacion == asignaciones_iot.id
    ).filter(
        riego.id_usuario == userId,
        asignaciones_iot.id_cultivo == idCultivo,
        riego.estado == True,
        riego.motivo_cierre == 'tiempo_maximo'
    ).order_by(riego.fecha_fin.desc().nullslast(), riego.fecha.desc()).first()
    
    tiempo_desde_ultimo_riego_seg = None
    ultimo_riego_fecha_fin = None
    if ultima_sesion:
        ahora_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        tiempo_desde_ultimo_riego_seg = max(0, int((ahora_naive - ultima_sesion.fecha).total_seconds()))
        ultimo_riego_fecha_fin = ultima_sesion.fecha.isoformat() + "Z"

    # Buscar sesión actualmente pausada
    sesion_pausada = db.query(riego).filter(
        riego.id_asignacion == id_bomba,
        riego.estado == False,
        riego.motivo_cierre.like("pausado_%")
    ).order_by(riego.id.desc()).first()

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
            content = motivo_str[len("pausado_"):]
            rparts = content.rsplit("_", 1)
            if len(rparts) == 2:
                pausado_motivo = rparts[0]
                try:
                    elapsed = int(rparts[1])
                except ValueError:
                    elapsed = pausado_tiempo_transcurrido
                pausado_tiempo_transcurrido = max(pausado_tiempo_transcurrido, elapsed)
                pausado_tiempo_restante = max(0, pausado_duracion_segundos - pausado_tiempo_transcurrido)
            else:
                pausado_motivo = content
                pausado_tiempo_restante = max(0, pausado_duracion_segundos - pausado_tiempo_transcurrido)
        else:
            pausado_motivo = "sin_agua"
            pausado_tiempo_restante = max(0, pausado_duracion_segundos - pausado_tiempo_transcurrido)

    # Buscar sesión de riego activa
    sesion_activa = db.query(riego).filter(
        riego.id_asignacion == id_bomba,
        riego.estado == False,
        (riego.motivo_cierre.is_(None)) | (~riego.motivo_cierre.like("pausado_%"))
    ).order_by(riego.id.desc()).first()

    riego_activo_payload = None
    if sesion_activa:
        from .irrigation import executed_seconds
        now_ref = datetime.now(timezone.utc).replace(tzinfo=None)
        elapsed_sec = executed_seconds(sesion_activa, now_ref)
        riego_activo_payload = {
            "id": sesion_activa.id,
            "segundosTranscurridos": elapsed_sec,
            "duracionSegundos": sesion_activa.duracion_segundos,
            "fechaInicio": sesion_activa.fecha_inicio.isoformat() + "Z" if sesion_activa.fecha_inicio else None,
            "fechaReferencia": now_ref.isoformat() + "Z"
        }

    # 7. Mapear dispositivos asociados a este cultivo
    dispositivos_map = {}
    for a in asigs:
        dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == a.id_dispositivo).first()
        if dev and dev.id_dispositivo not in dispositivos_map:
            tipo = db.query(tipos_dispositivo).filter(tipos_dispositivo.id == dev.id_tipo).first()
            tipo_nombre = tipo.nombre if tipo else ""
            
            # Buscar componentes asignados
            componentes_asig = []
            for a2 in asigs:
                if a2.id_dispositivo == dev.id_dispositivo and a2.id_componente is not None:
                    comp = db.query(componentes).filter(componentes.id == a2.id_componente).first()
                    if comp:
                        tipo_comp = db.query(tipos_componente).filter(tipos_componente.id == comp.id_tipo_componente).first()
                        componentes_asig.append({
                            "id": comp.id,
                            "nombre": tipo_comp.nombre_modelo if tipo_comp else "Desconocido",
                            "categoria": tipo_comp.categoria if tipo_comp else "",
                            "pin": a2.pin_gpio if a2.pin_gpio is not None else "N/A"
                        })
                        
            funcionamiento_activo = any(a2.activo for a2 in asigs if a2.id_dispositivo == dev.id_dispositivo)
            
            dispositivos_map[dev.id_dispositivo] = {
                "id": dev.id_dispositivo,
                "nombre": dev.nombre,
                "mac": dev.mac_address if dev.mac_address else "N/A",
                "funcionamientoActivo": funcionamiento_activo,
                "estado": dev.estado if dev.estado else "offline",
                "tipoId": dev.id_tipo,
                "tipoNombre": tipo_nombre,
                "sensores": componentes_asig
            }
            
    return {
        "bomba": {
            "id": id_bomba,
            "pin": pin_gpio,
            "online": estado_dispositivo == "activo",
            "encendida": bomba_encendida,
            "timeoutMin": timeout_min
        },
        "valvula": {
            "id": id_bomba,
            "pin": 25,
            "abierta": valvula_abierta,
            "modoAuto": True
        },
        "seguridad": {
            "esInvestigador": esInvestigador,
            "esAdmin": esAdmin
        },
        "modo": {
            "actual": modo_actual,
            "manualActivo": manual_act,
            "predictivoActivo": predictivo_activo,
            "programadoActivo": programado_act,
            "tieneModelo": tiene_modelo
        },
        "cooldownMinutos": int(os.getenv("ML_IRRIGATION_COOLDOWN_MINUTES", "30")),
        "tiempoDesdeUltimoRiegoSeg": tiempo_desde_ultimo_riego_seg,
        "ultimoRiegoFechaFin": ultimo_riego_fecha_fin,
        "sesionPausada": {
            "activa": es_pausado,
            "motivo": pausado_motivo,
            "segundosTranscurridos": pausado_tiempo_transcurrido,
            "duracionSegundos": pausado_duracion_segundos,
            "tiempoRestanteSeg": pausado_tiempo_restante
        },
        "logs": logs_unificados,
        "horarios": horarios,
        "dispositivos": list(dispositivos_map.values()),
        "ultimaPrediccion": pred_dict,
        "riegoActivo": riego_activo_payload
    }


def establecer_modo_operacion(db: Session, userId: int, id_bomba: int, modo: str, idCultivo: int | None = None) -> dict:
    modo = modo.lower()
    
    if idCultivo is None:
        asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == id_bomba).first()
        idCultivo = asig.id_cultivo if asig else None
        
    # Desactivar modelo si cambiamos a manual o programado
    if modo in ['manual', 'programado']:
        db.query(cultivo_modelo).filter(
            cultivo_modelo.id_usuario == userId,
            cultivo_modelo.id_cultivo == idCultivo
        ).update({"activo": False})
        
    # Desactivar programaciones si cambiamos a manual o predictivo
    if modo in ['manual', 'predictivo']:
        db.query(programacion_riego).filter(
            programacion_riego.id_usuario == userId,
            programacion_riego.id_asignacion == id_bomba
        ).update({"activo": False})
        
    # Activar modelo si elegimos predictivo
    if modo == 'predictivo':
        usr_mod = db.query(cultivo_modelo).filter(
            cultivo_modelo.id_usuario == userId,
            cultivo_modelo.id_cultivo == idCultivo
        ).order_by(cultivo_modelo.fecha_asignacion.desc()).first()
        if usr_mod:
            usr_mod.activo = True
        else:
            primer_modelo = db.query(modelos_ml).order_by(modelos_ml.id_modelo.asc()).first()
            id_mod = primer_modelo.id_modelo if primer_modelo else 1
            nuevo_usr_mod = cultivo_modelo(
                id_usuario=userId,
                id_cultivo=idCultivo,
                id_modelo=id_mod,
                activo=True
            )
            db.add(nuevo_usr_mod)
            
        # EJECUTAR PREDICCIÓN ML EN VIVO DE INMEDIATO
        try:
            asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == id_bomba).first()
            if asig and asig.activo:
                # Cargar las asignaciones de sensores (tipo 1) para este cultivo
                sensor_asigs = db.query(asignaciones_iot).join(dispositivos).filter(
                    asignaciones_iot.id_cultivo == idCultivo,
                    dispositivos.id_tipo == 1
                ).all()
                sensor_asig_ids = [sa.id for sa in sensor_asigs]
                
                if sensor_asig_ids:
                    from src.db.models import humedad_suelo, humedad_ambiente, temperatura_ambiente, temperatura_suelo
                    h_suelo = db.query(humedad_suelo).filter(humedad_suelo.id_asignacion.in_(sensor_asig_ids)).order_by(humedad_suelo.id.desc()).first()
                    h_amb = db.query(humedad_ambiente).filter(humedad_ambiente.id_asignacion.in_(sensor_asig_ids)).order_by(humedad_ambiente.id.desc()).first()
                    t_amb = db.query(temperatura_ambiente).filter(temperatura_ambiente.id_asignacion.in_(sensor_asig_ids)).order_by(temperatura_ambiente.id.desc()).first()
                    t_suelo = db.query(temperatura_suelo).filter(temperatura_suelo.id_asignacion.in_(sensor_asig_ids)).order_by(temperatura_suelo.id.desc()).first()
                    
                    from src.schemas.ml import PrediccionRiegoModel
                    pred_input = PrediccionRiegoModel(
                        humedad_suelo=float(h_suelo.valor) if h_suelo and h_suelo.valor is not None else 0.0,
                        humedad_ambiente=float(h_amb.valor) if h_amb and h_amb.valor is not None else 0.0,
                        temperatura_ambiente=float(t_amb.temperatura) if t_amb and t_amb.temperatura is not None else 0.0,
                        temperatura_suelo=float(t_suelo.temperatura) if t_suelo and t_suelo.temperatura is not None else 0.0,
                    )
                    
                    from src.api.routers.ml import obtener_prediccion_riego
                    resultado = obtener_prediccion_riego(
                        data=pred_input,
                        db=db,
                        id_usuario=userId,
                        id_cultivo=idCultivo,
                        id_dispositivo=asig.id_dispositivo
                    )
                    
                    # Si la recomendación es regar, iniciar el riego
                    if resultado.get("recomendacion") == "regar":
                        from src.services.irrigation import start_irrigation
                        start_irrigation(
                            db=db,
                            assignment=asig,
                            irrigation_type="automatico_ml",
                            model_id=resultado.get("id_modelo"),
                            prediction_id=resultado.get("id_prediccion")
                        )
        except Exception as e:
            pass
            
    # Activar programaciones si elegimos programado
    if modo == 'programado':
        db.query(programacion_riego).filter(
            programacion_riego.id_usuario == userId,
            programacion_riego.id_asignacion == id_bomba
        ).update({"activo": True})
        
    # Auditoría
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion=f"Cambio de modo a {modo}",
        modulo="Control y Configuración",
        descripcion=f"El usuario cambió el modo de operación de riego a {modo}."
    )
    db.add(nuevo_log)
    db.commit()

    # Enviar comando MQTT al ESP32
    asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == id_bomba).first()
    if asig:
        try:
            import json
            payload = json.dumps({"accion": "CAMBIO_MODO", "modo": modo})
            _publish_relay_command(asig, payload)
        except Exception as mqtt_err:
            pass

    return {"status": "ok", "message": f"Modo de operación cambiado a {modo}."}


def conmutar_bomba_manual(db: Session, userId: int, idBomba: int, encender: bool) -> dict:
    asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == idBomba).first()
    if not asig or asig.id_usuario != userId:
        raise ValueError("Asignacion de bomba no encontrada.")

    if encender:
        session = start_irrigation(db, asig, "manual")
        timeout_min = max((session.duracion_segundos or 0) // 60, MIN_RELAY_MINUTES)
    else:
        stop_irrigation(db, asig, "apagado_manual")
        timeout_min = get_max_relay_seconds(db, userId, asig.id_cultivo) // 60
                
    # 4. Auditoría
    accion_str = "Encendido manual de bomba" if encender else "Apagado manual de bomba"
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion=accion_str,
        modulo="Control y Configuración",
        descripcion=f"El usuario forzó el estado del actuador a {'ON' if encender else 'OFF'}."
    )
    db.add(nuevo_log)
    db.commit()
    return {
        "status": "ok",
        "message": f"Bomba conmutada a {'ON' if encender else 'OFF'}.",
        "timeoutMin": timeout_min,
    }


def conmutar_valvula_manual(db: Session, userId: int, idBomba: int, abrir: bool) -> dict:
    asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == idBomba).first()
    if not asig or asig.id_usuario != userId:
        raise ValueError("Asignacion de actuador no encontrada.")

    config = db.query(configuracion_tanque).filter(
        configuracion_tanque.id_asignacion == asig.id
    ).first()
    if not config:
        raise ValueError("Configuracion de tanque no encontrada.")

    config.valvula_abierta = abrir
    db.add(config)
    _publish_relay_command(asig, build_valve_command(abrir))

    accion_str = "Apertura manual de valvula" if abrir else "Cierre manual de valvula"
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion=accion_str,
        modulo="Control y Configuracion",
        descripcion=f"El usuario forzo el estado de la valvula a {'ON' if abrir else 'OFF'}."
    )
    db.add(nuevo_log)
    db.commit()
    return {"status": "ok", "message": f"Valvula conmutada a {'ON' if abrir else 'OFF'}."}


def actualizar_tiempo_maximo_rele(
    db: Session, userId: int, idCultivo: int, duracionMin: int
) -> dict:
    if not MIN_RELAY_MINUTES <= duracionMin <= MAX_RELAY_MINUTES:
        raise ValueError(
            f"La duracion debe estar entre {MIN_RELAY_MINUTES} y {MAX_RELAY_MINUTES} minutos."
        )

    config = db.query(configuracion_control).filter(
        configuracion_control.id_usuario == userId,
        configuracion_control.id_cultivo == idCultivo,
    ).first()
    if config is None:
        config = configuracion_control(
            id_usuario=userId,
            id_cultivo=idCultivo,
            duracion_riego_max_seg=duracionMin * 60,
        )
    else:
        config.duracion_riego_max_seg = duracionMin * 60
        config.actualizado_en = datetime.now()
    db.add(config)
    db.add(logs_sistema(
        id_usuario=userId,
        accion="Actualizacion de tiempo maximo del rele",
        modulo="Control y Configuracion",
        descripcion=f"Tiempo maximo del rele actualizado a {duracionMin} minutos para el cultivo {idCultivo}.",
    ))
    db.commit()
    return {"status": "ok", "duracionMaxMinutos": duracionMin}


def crear_horario_riego(db: Session, userId: int, idBomba: int, hora: str, duracionMin: int, dias: List[bool], nombre: str | None = None) -> dict:
    h_str, m_str = hora.split(':')
    h = int(h_str)
    m = int(m_str)
    
    fecha_ini = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
    
    if duracionMin < MIN_RELAY_MINUTES or duracionMin > MAX_RELAY_MINUTES:
        raise ValueError(
            f"La duracion del horario debe estar entre {MIN_RELAY_MINUTES} y {MAX_RELAY_MINUTES} minutos."
        )
    
    # Resolver id_cultivo desde la asignación del actuador/bomba
    asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == idBomba).first()
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
        domingo=dias[6]
    )
    db.add(nuevo_horario)
    
    # Auditoría
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion="Creación de horario de riego",
        modulo="Control y Configuración",
        descripcion=f"Se creó una programación de riego llamada '{nombre or 'Sin nombre'}' a las {hora} por {duracionMin} minutos."
    )
    db.add(nuevo_log)
    db.commit()
    return {"status": "ok", "message": "Horario agregado con éxito."}


def actualizar_horario_riego(db: Session, userId: int, id_horario: int, hora: str, duracionMin: int, dias: List[bool], nombre: str | None = None) -> dict | None:
    horario = db.query(programacion_riego).filter(
        programacion_riego.id == id_horario,
        programacion_riego.id_usuario == userId
    ).first()
    
    if not horario:
        return None
        
    h_str, m_str = hora.split(':')
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
    
    db.add(horario)
    
    # Auditoría
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion="Actualización de horario de riego",
        modulo="Control y Configuración",
        descripcion=f"Se actualizó la programación de riego ID {id_horario} llamada '{nombre or 'Sin nombre'}' a las {hora} por {duracionMin} minutos."
    )
    db.add(nuevo_log)
    db.commit()
    return {"status": "ok", "message": "Horario actualizado con éxito."}


def conmutar_horario_riego(db: Session, userId: int, id_horario: int, activo: bool) -> dict | None:
    horario = db.query(programacion_riego).filter(
        programacion_riego.id == id_horario,
        programacion_riego.id_usuario == userId
    ).first()
    
    if not horario:
        return None
        
    horario.activo = activo
    db.add(horario)
    
    # Auditoría
    accion_str = "Activación de horario de riego" if activo else "Desactivación de horario de riego"
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion=accion_str,
        modulo="Control y Configuración",
        descripcion=f"Se {'activó' if activo else 'desactivó'} el horario de riego ID: {id_horario}."
    )
    db.add(nuevo_log)
    db.commit()
    return {"status": "ok", "message": f"Horario {'activado' if activo else 'desactivado'}."}


def eliminar_horario_riego(db: Session, userId: int, id_horario: int) -> dict | None:
    horario = db.query(programacion_riego).filter(
        programacion_riego.id == id_horario,
        programacion_riego.id_usuario == userId
    ).first()
    
    if not horario:
        return None
        
    db.delete(horario)
    
    # Auditoría
    nuevo_log = logs_sistema(
        id_usuario=userId,
        accion="Eliminación de horario de riego",
        modulo="Control y Configuración",
        descripcion=f"Se eliminó el horario de riego ID: {id_horario}."
    )
    db.add(nuevo_log)
    db.commit()
    return {"status": "ok", "message": "Horario eliminado."}


def conmutar_bomba_por_telemetria(db: Session, userId: int, id_telemetria: int, estado: bool) -> dict | None:
    # 1. Actualizar telemetria_tanque
    telemetria = db.query(telemetria_tanque).filter(telemetria_tanque.id == id_telemetria).first()
    if not telemetria:
        return None
        
    telemetria.bomba_encendida = estado
    db.add(telemetria)
    
    # 2. Obtener asignación para conocer el cultivo y bomba
    asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == telemetria.id_asignacion).first()
    pump_assignment = None
    if asig:
        pump_assignment = db.query(asignaciones_iot).join(
            configuracion_tanque,
            configuracion_tanque.id_asignacion == asignaciones_iot.id,
        ).filter(
            asignaciones_iot.id_dispositivo == asig.id_dispositivo,
            asignaciones_iot.id_usuario == userId,
        ).first()
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
        descripcion=f"Actualización de bomba desde widget de Tanque (Telemetría ID: {id_telemetria})"
    )
    db.add(nuevo_log)
    db.commit()
    return {"status": "ok", "message": f"Bomba conmutada a {'ON' if estado else 'OFF'}."}


def actualizar_umbrales_riego(db: Session, userId: int, id_cultivo: int, updates: List[Any]) -> dict:
    for u in updates:
        db.query(configuracion_umbrales).filter(
            configuracion_umbrales.id == u.id,
            configuracion_umbrales.id_usuario == userId,
            configuracion_umbrales.id_cultivo == id_cultivo
        ).update({
            "valor_minimo": u.min,
            "valor_maximo": u.max,
            "actualizado_en": datetime.now()
        })
    db.commit()
    return {"status": "ok", "message": "Umbrales actualizados con éxito."}
