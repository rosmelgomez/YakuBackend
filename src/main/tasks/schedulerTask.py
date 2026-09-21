import asyncio
import logging

from src.main.db.databaseConexion import SessionLocal
from src.main.service import horarioServ, schedulerServ

logger = logging.getLogger(__name__)

# La seguridad del rele (apagar por duracion maxima) necesita resolucion fina,
# pero el cooldown de riego ML se mide en minutos (tipicamente 30-120), asi
# que evaluarlo cada 10s es innecesario: solo genera carga y evaluaciones
# repetidas mientras el cooldown sigue vigente. Se revisa aparte cada minuto.
ML_CHECK_INTERVAL_SECONDS = 60


def _run_scheduler_cycle():
    db = SessionLocal()
    try:
        schedulerServ.check_durations(db)
        horarioServ.verificar_horarios_pendientesServ(db)
    except Exception:
        logger.exception("Error en ciclo del planificador")
    finally:
        db.close()


def _run_ml_cycle():
    db = SessionLocal()
    try:
        schedulerServ.check_ml_cooldown_and_irrigate(db)
    except Exception:
        logger.exception("Error en ciclo de evaluación ML")
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
    logger.info(
        "[SCHEDULER ML] Bucle de evaluación de cooldown ML iniciado (cada %ss).",
        ML_CHECK_INTERVAL_SECONDS,
    )
    while True:
        try:
            await asyncio.sleep(ML_CHECK_INTERVAL_SECONDS)
            await asyncio.to_thread(_run_ml_cycle)
        except asyncio.CancelledError:
            logger.info("[SCHEDULER ML] Tarea de evaluación ML cancelada.")
            break
        except Exception:
            logger.exception("Error en bucle de evaluación ML")


def start_scheduler():
    asyncio.create_task(scheduler_loop())
    asyncio.create_task(ml_scheduler_loop())
