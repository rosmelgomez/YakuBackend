from datetime import datetime
from typing import List, Any
from sqlalchemy.orm import Session

from ..models.models import (
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
    umbrales_config,
    modelos_ml
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
        id_bomba = a.id
    else:
        pin_gpio = "N/A"
        estado_dispositivo = "offline"
        bomba_encendida = False
        id_bomba = None
        
    # 3. Timeout config
    config_c = db.query(configuracion_control).filter(
        configuracion_control.id_usuario == userId,
        configuracion_control.id_cultivo == idCultivo
    ).first()
    timeout_min = (config_c.duracion_riego_max_seg // 60) if (config_c and config_c.duracion_riego_max_seg is not None) else 10
    
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
        "logs": logs_unificados,
        "horarios": horarios,
        "dispositivos": list(dispositivos_map.values())
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
    return {"status": "ok", "message": f"Modo de operación cambiado a {modo}."}


def conmutar_bomba_manual(db: Session, userId: int, idBomba: int, encender: bool) -> dict:
    # 1. Actualizar el actuador físico
    config_t = db.query(configuracion_tanque).filter(configuracion_tanque.id_asignacion == idBomba).first()
    if not config_t:
        config_t = configuracion_tanque(id_asignacion=idBomba, bomba_encendida=encender, actualizado_en=datetime.now())
        db.add(config_t)
        db.flush()
    else:
        config_t.bomba_encendida = encender
        config_t.actualizado_en = datetime.now()
        db.add(config_t)
        
    # Obtener asignación para saber el cultivo
    asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == idBomba).first()
    
    # 2. SINCRONIZACIÓN: Actualizar el registro más reciente de telemetría de ese cultivo
    if asig and asig.id_cultivo:
        sensor_tanque = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_cultivo == asig.id_cultivo
        ).first()
        if sensor_tanque:
            ult_telemetria = db.query(telemetria_tanque).filter(
                telemetria_tanque.id_asignacion == sensor_tanque.id
            ).order_by(telemetria_tanque.fecha.desc()).first()
            if ult_telemetria:
                ult_telemetria.bomba_encendida = encender
                db.add(ult_telemetria)
                
        # 3. Mandar señal física vía MQTT al dispositivo asociado
        dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == asig.id_dispositivo).first()
        if dev:
            topic = dev.topic_sub or "yaku/valvula/comando"
            payload = "ON" if encender else "OFF"
            try:
                from src.tasks.mqtt_subscriber import publish_mqtt_message
                publish_mqtt_message(topic, payload, qos=1, retain=True)
            except Exception as mq_err:
                print(f"[MQTT WARNING] Error enviando comando de bomba: {mq_err}")
                
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
    return {"status": "ok", "message": f"Bomba conmutada a {'ON' if encender else 'OFF'}."}


def crear_horario_riego(db: Session, userId: int, idBomba: int, hora: str, duracionMin: int, dias: List[bool], nombre: str | None = None) -> dict:
    h_str, m_str = hora.split(':')
    h = int(h_str)
    m = int(m_str)
    
    fecha_ini = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
    
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
    if asig and asig.id_cultivo:
        # Buscar la bomba de este cultivo
        bomba_asig = db.query(asignaciones_iot).filter(
            asignaciones_iot.id_cultivo == asig.id_cultivo,
            asignaciones_iot.id_usuario == userId
        ).all()
        
        for b in bomba_asig:
            config_t = db.query(configuracion_tanque).filter(configuracion_tanque.id_asignacion == b.id).first()
            if config_t:
                config_t.bomba_encendida = estado
                config_t.actualizado_en = datetime.now()
                db.add(config_t)
                
                # Mandar señal física vía MQTT al dispositivo asociado
                dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == b.id_dispositivo).first()
                if dev:
                    topic = dev.topic_sub or "yaku/valvula/comando"
                    payload = "ON" if estado else "OFF"
                    try:
                        from src.tasks.mqtt_subscriber import publish_mqtt_message
                        publish_mqtt_message(topic, payload, qos=1, retain=True)
                    except Exception as mq_err:
                        print(f"[MQTT WARNING] Error enviando comando de bomba por telemetria: {mq_err}")
                        
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
        db.query(umbrales_config).filter(
            umbrales_config.id == u.id,
            umbrales_config.id_usuario == userId,
            umbrales_config.id_cultivo == id_cultivo
        ).update({
            "valor_minimo": u.min,
            "valor_maximo": u.max,
            "actualizado_en": datetime.now()
        })
    db.commit()
    return {"status": "ok", "message": "Umbrales actualizados con éxito."}
