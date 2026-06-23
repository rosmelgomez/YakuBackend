"""Recrea la base de datos local de desarrollo.

Este comando es destructivo y se niega a ejecutarse cuando APP_ENV=production.
"""

import logging
import os
import re
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()
logger = logging.getLogger(__name__)


def main() -> int:
    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        logger.error("La recreación de la base de datos está bloqueada en producción")
        return 1

    db_user = os.getenv("DB_USER", "").strip()
    db_pass = os.getenv("DB_PASSWORD", "")
    db_host = os.getenv("DB_HOST", "127.0.0.1").strip()
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_name = os.getenv("DB_NAME", "").strip()
    if not db_user or not db_pass or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", db_name):
        logger.error("DB_USER, DB_PASSWORD y un DB_NAME válido son obligatorios")
        return 1

    postgres_url = URL.create(
        "postgresql+psycopg2",
        username=db_user,
        password=db_pass,
        host=db_host,
        port=db_port,
        database="postgres",
    )
    engine_postgres = create_engine(postgres_url, pool_pre_ping=True)

    try:
        logger.warning("Recreando la base de datos de desarrollo", extra={"database": db_name})
        with engine_postgres.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{db_name}"'))

        from src.db.database import Base, engine as app_engine
        import src.db.models  # noqa: F401

        Base.metadata.create_all(bind=app_engine)

        from seed import ejecutar_semillas
        if not ejecutar_semillas():
            return 1
    except Exception:
        logger.exception("No se pudo recrear la base de datos")
        return 1
    finally:
        engine_postgres.dispose()

    logger.info("Base de datos de desarrollo recreada correctamente")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    raise SystemExit(main())
