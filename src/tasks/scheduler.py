import asyncio
from datetime import datetime
from sqlalchemy.orm import Session

from src.models.database import SessionLocal
from src.models.models import programacion_riego, asignaciones_iot, configuracion_control, riego

async def scheduler_loop():
    print("[SCHEDULER] Bucle del planificador de riego iniciado.")
    while True:
        try:
            # Esperar 10 segundos
            await asyncio.sleep(10)
            
            db = SessionLocal()
            try:
                check_schedules(db)
                check_durations(db)
            except Exception as loop_err:
                print(f"[SCHEDULER] Error en ciclo del planificador: {loop_err}")
            finally:
                db.close()
        except asyncio.CancelledError:
            print("[SCHEDULER] Tarea del planificador cancelada.")
            break
        except Exception as e:
            print(f"[SCHEDULER] Error en bucle: {e}")

def check_schedules(db: Session):
    now = datetime.now()
    current_weekday = now.weekday()  # 0 = Lunes, ..., 6 = Domingo
    day_attrs = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
    day_attr = day_attrs[current_weekday]
    
    current_time_str = now.strftime("%H:%M")
    
    active_schedules = db.query(programacion_riego).filter(programacion_riego.activo == True).all()
    for sched in active_schedules:
        # Verificar si hoy está activo en la programación
        if not getattr(sched, day_attr, False):
            continue
            
        # Verificar si la hora de inicio coincide (HH:MM)
        sched_time_str = sched.hora_inicio.strftime("%H:%M")
        if sched_time_str != current_time_str:
            continue
            
        # Evitar múltiples activaciones en el mismo minuto
        if sched.ultima_ejecucion:
            if sched.ultima_ejecucion.strftime("%Y-%m-%d %H:%M") == now.strftime("%Y-%m-%d %H:%M"):
                continue
                
        # Verificar si la asignación está activa
        asig = db.query(asignaciones_iot).filter(
            asignaciones_iot.id == sched.id_asignacion,
            asignaciones_iot.activo == True
        ).first()
        if not asig:
            continue
            
        # Obtener dispositivo asociado
        dispositivo = asig.dispositivo
        if not dispositivo:
            continue
            
        print(f"[SCHEDULER] Iniciando riego programado para la asignación {sched.id_asignacion} (Horario: {sched_time_str})")
        sched.ultima_ejecucion = now
        db.add(sched)
        
        # Publicar comando ON vía MQTT
        topic = dispositivo.topic_sub or "yaku/riego/comando"
        try:
            from src.tasks.mqtt_subscriber import publish_mqtt_message
            publish_mqtt_message(topic, "ON", qos=1, retain=True)
        except Exception as mq_err:
            print(f"[SCHEDULER] Error enviando comando ON a MQTT: {mq_err}")
            
    db.commit()

def check_durations(db: Session):
    now = datetime.now()
    # Buscar sesiones de riego programadas en progreso (estado = False)
    active_sessions = db.query(riego).filter(
        riego.estado == False,
        riego.tipo_riego == 'programado'
    ).all()
    
    for session in active_sessions:
        asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == session.id_asignacion).first()
        if not asig:
            continue
            
        # Obtener la duración desde la programación activa
        sched = db.query(programacion_riego).filter(
            programacion_riego.id_asignacion == session.id_asignacion,
            programacion_riego.activo == True
        ).first()
        
        duracion_seg = sched.duracion_seg if sched else 300
        
        elapsed = (now - session.fecha).total_seconds()
        if elapsed >= duracion_seg:
            print(f"[SCHEDULER] Tiempo de riego programado expirado ({elapsed}s >= {duracion_seg}s) para asignación {session.id_asignacion}. Enviando comando de apagado.")
            
            dispositivo = asig.dispositivo
            if dispositivo:
                topic = dispositivo.topic_sub or "yaku/riego/comando"
                try:
                    from src.tasks.mqtt_subscriber import publish_mqtt_message
                    publish_mqtt_message(topic, "OFF", qos=1, retain=True)
                except Exception as mq_err:
                    print(f"[SCHEDULER] Error enviando comando OFF a MQTT: {mq_err}")

def start_scheduler():
    asyncio.create_task(scheduler_loop())
