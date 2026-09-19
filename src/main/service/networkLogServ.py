"""Registro de errores de red (broker MQTT) para monitoreo administrativo (HU-35).

Los callbacks del cliente MQTT (paho-mqtt) corren en su propio hilo, fuera del
ciclo de vida de una request de FastAPI, por lo que este módulo abre y cierra
su propia sesión de base de datos en cada llamada.
"""

import logging

logger = logging.getLogger(__name__)

MODULO_RED = "Red MQTT"


def registrar_evento_red(accion: str, mensaje: str) -> None:
    """Best-effort: nunca debe romper el flujo de conexión/publicación MQTT
    si falla al escribir en la base de datos."""
    try:
        from src.main.db.databaseConexion import SessionLocal
        from src.main.model.models import logs_sistema
        from src.main.repositories import sessionRep as session_repository

        db = SessionLocal()
        try:
            session_repository.add(
                db,
                logs_sistema(
                    id_usuario=None,
                    accion=accion,
                    modulo=MODULO_RED,
                    descripcion=mensaje,
                ),
            )
            session_repository.commit(db)
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"No se pudo registrar evento de red en auditoría: {exc}")
