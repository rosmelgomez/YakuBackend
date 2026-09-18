import asyncio
import logging

from src.main.db.databaseConexion import SessionLocal
from src.main.service import horarioServ, schedulerServ

logger = logging.getLogger(__name__)


def _run_scheduler_cycle():
    db = SessionLocal()
    try:
        schedulerServ.check_durations(db)
        schedulerServ.check_ml_cooldown_and_irrigate(db)
        horarioServ.verificar_horarios_pendientesServ(db)
    except Exception:
        logger.exception("Error en ciclo del planificador")
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


def start_scheduler():
    asyncio.create_task(scheduler_loop())
