import asyncio
import logging

from src.main.db.databaseConexion import SessionLocal
from src.main.service import horarioServ, schedulerServ

logger = logging.getLogger(__name__)

# La seguridad del rele (apagar por duracion maxima) necesita resolucion fina,
# pero el cooldown de riego ML se mide en minutos (tipicamente 30-120), asi
# que evaluarlo cada 10s es innecesario. En vez de un intervalo fijo, el
# propio schedulerServ.check_ml_cooldown_and_irrigate calcula cuanto falta
# para que el cooldown configurado de cada cultivo se cumpla y devuelve ese
# tiempo dinamicamente; este valor por defecto solo se usa como fallback si
# la funcion no pudo determinar un tiempo (p.ej. primera vuelta o error).
ML_CHECK_FALLBACK_SECONDS = 60


def _run_scheduler_cycle():
    db = SessionLocal()
    try:
        schedulerServ.check_durations(db)
        horarioServ.verificar_horarios_pendientesServ(db)
    except Exception:
        logger.exception("Error en ciclo del planificador")
    finally:
        db.close()


def _run_ml_cycle() -> int:
    db = SessionLocal()
    try:
        return schedulerServ.check_ml_cooldown_and_irrigate(db)
    except Exception:
        logger.exception("Error en ciclo de evaluación ML")
        return ML_CHECK_FALLBACK_SECONDS
    finally:
        db.close()


async def scheduler_loop():
    logger.info("[SCHEDULER] Bucle del planificador de riego iniciado.")
    while True:
        try:
            # Esperar 10 segundos
            await asyncio.sleep(10)
            await asyncio.to_thread(_run_scheduler_cycle)
        except asyncio.CancelledError:
            logger.info("[SCHEDULER] Tarea del planificador cancelada.")
            break
        except Exception:
            logger.exception("Error en bucle del planificador")


async def ml_scheduler_loop():
    logger.info("[SCHEDULER ML] Bucle de evaluación de cooldown ML iniciado (intervalo dinámico).")
    wait_seconds = ML_CHECK_FALLBACK_SECONDS
    while True:
        try:
            await asyncio.sleep(wait_seconds)
            wait_seconds = await asyncio.to_thread(_run_ml_cycle)
            if not wait_seconds or wait_seconds <= 0:
                wait_seconds = ML_CHECK_FALLBACK_SECONDS
        except asyncio.CancelledError:
            logger.info("[SCHEDULER ML] Tarea de evaluación ML cancelada.")
            break
        except Exception:
            logger.exception("Error en bucle de evaluación ML")
            wait_seconds = ML_CHECK_FALLBACK_SECONDS


def start_scheduler():
    asyncio.create_task(scheduler_loop())
    asyncio.create_task(ml_scheduler_loop())
