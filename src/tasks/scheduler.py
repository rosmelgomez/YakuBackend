import asyncio
from datetime import datetime
import logging
from sqlalchemy.orm import Session

from src.db.database import SessionLocal
from src.db.models import programacion_riego, asignaciones_iot, riego
logger = logging.getLogger(__name__)

from src.services.irrigation import (
    get_max_relay_seconds,
    start_irrigation,
    stop_irrigation,
)

async def scheduler_loop():
    logger.info("[SCHEDULER] Bucle del planificador de riego iniciado.")
    while True:
        try:
            # Esperar 10 segundos
            await asyncio.sleep(10)
            
            db = SessionLocal()
            try:
                check_schedules(db)
                check_durations(db)
            except Exception:
                logger.exception("Error en ciclo del planificador")
            finally:
                db.close()
        except asyncio.CancelledError:
            logger.info("[SCHEDULER] Tarea del planificador cancelada.")
            break
        except Exception:
            logger.exception("Error en bucle del planificador")

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
            
        logger.info(f"[SCHEDULER] Iniciando riego programado para la asignación {sched.id_asignacion} (Horario: {sched_time_str})")
        try:
            start_irrigation(
                db,
                asig,
                "programado",
                requested_seconds=sched.duracion_seg,
            )
            sched.ultima_ejecucion = now
            db.add(sched)
        except Exception:
            db.rollback()
            logger.exception("Error iniciando riego programado")
            
    db.commit()

def check_durations(db: Session):
    now = datetime.now()
    # Todas las formas de riego comparten el mismo limite de seguridad del rele.
    active_sessions = db.query(riego).filter(
        riego.estado == False
    ).all()
    
    for session in active_sessions:
        asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == session.id_asignacion).first()
        if not asig:
            continue
            
        maximum = get_max_relay_seconds(db, session.id_usuario, asig.id_cultivo)
        stored_duration = session.duracion_segundos or maximum
        duracion_seg = min(max(int(stored_duration), 60), maximum)
            
        elapsed = (now - session.fecha).total_seconds()
        if elapsed >= duracion_seg:
            logger.info(f"[SCHEDULER] Tiempo de riego {session.tipo_riego} expirado ({elapsed}s >= {duracion_seg}s) para asignación {session.id_asignacion}. Enviando comando de apagado.")
            
            try:
                stop_irrigation(db, asig, "tiempo_maximo")
            except Exception:
                db.rollback()
                logger.exception("Error apagando el relé por duración máxima")

def start_scheduler():
    asyncio.create_task(scheduler_loop())
