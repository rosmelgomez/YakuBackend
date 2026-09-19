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

        if bootstrapRep.database_empty():
            logger.info(
                "Base de datos sin datos base detectada; cargando catálogos y datos desde yaku_data.sql..."
            )
            from seed import ejecutar_semillas

            ejecutar_semillas()

        bootstrapRep.run_migrations()
        bootstrapRep.ensure_base_catalogs()
        bootstrapRep.ensure_default_admin()
        bootstrapRep.ensure_irrigation_execution_schema()
        bootstrapRep.ensure_feedback_schema()
        bootstrapRep.ensure_soil_ambient_umbrales_only()
        bootstrapRep.ensure_active_notification_types()
        bootstrapRep.ensure_permisos_schema()
        bootstrapRep.ensure_performance_indexes()

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

        mqtt_db = SessionLocal()
        try:
            from src.main.service.mqttConfigServ import obtener_configuracion_efectiva

            mqtt_overrides = obtener_configuracion_efectiva(mqtt_db)
        except Exception as e:
            logger.warning(
                f"No se pudo cargar la configuración MQTT desde la base de datos, usando .env: {e}"
            )
            mqtt_overrides = None
        finally:
            mqtt_db.close()

        start_mqtt(overrides=mqtt_overrides)
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
