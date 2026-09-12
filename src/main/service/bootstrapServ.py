"""Inicialización de base de datos, firmware y tareas de Yaku."""

import logging

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.main.core.yakuConfig import AUTO_CREATE_TABLES, IS_PRODUCTION
from src.main.repositories import bootstrapRep
from src.main.tasks.mqttSubscriberTask import start_mqtt

logger = logging.getLogger(__name__)


def initialize_backend():
    try:
        if AUTO_CREATE_TABLES or not bootstrapRep.tables_exist():
            bootstrapRep.create_tables()
        else:
            bootstrapRep.check_connection()

        bootstrapRep.run_migrations()
        bootstrapRep.ensure_base_catalogs()
        bootstrapRep.ensure_irrigation_execution_schema()
        bootstrapRep.ensure_feedback_schema()

        if not IS_PRODUCTION:
            db_empty = bootstrapRep.database_empty()
            if db_empty:
                logger.info(
                    "Base de datos vacía detectada; cargando datos de desarrollo"
                )
                from seed import ejecutar_semillas

                ejecutar_semillas()

        # Sincronización de firmwares en disco con la BD
        from src.main.db.databaseConexion import SessionLocal
        from src.main.service.firmwareServ import sincronizar_firmwares_disco

        db = SessionLocal()
        try:
            sincronizar_firmwares_disco(db)
        except Exception as e:
            logger.error(f"Error durante la sincronización de firmwares: {e}")
        finally:
            db.close()

        start_mqtt()
        from src.main.tasks.schedulerTask import start_scheduler

        start_scheduler()
    except OperationalError as exc:
        if IS_PRODUCTION:
            raise RuntimeError(
                "PostgreSQL no está disponible durante el arranque"
            ) from exc
        logger.warning(
            "PostgreSQL no está disponible; los servicios dependientes quedan deshabilitados"
        )
    except SQLAlchemyError as exc:
        raise RuntimeError("Error al inicializar la base de datos") from exc
