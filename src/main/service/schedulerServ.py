import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

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
        if pump_assignment.id != session.id_asignacion:
            logger.info(
                "[SCHEDULER] Ignorando sesion de riego asociada a sensor/no-bomba "
                f"Sesion={session.id}, asignacion={session.id_asignacion}, bomba={pump_assignment.id}."
            )
            continue

        maximum = get_max_relay_seconds(
            db, session.id_usuario, pump_assignment.id_cultivo
        )
        stored_duration = planned_seconds(session) or maximum
        duracion_seg = min(max(int(stored_duration), 60), maximum)

        elapsed = executed_seconds(session, now)
        if elapsed >= duracion_seg:
            logger.info(
                f"[SCHEDULER] Tiempo de riego {session.tipo_riego} expirado ({elapsed}s >= {duracion_seg}s) para asignación {session.id_asignacion}. Enviando comando de apagado."
            )

            try:
                stop_irrigation(db, pump_assignment, "tiempo_maximo")
            except Exception:
                session_repository.rollback(db)
                logger.exception("Error apagando el relé por duración máxima")
