"""Fixtures de integración: base de datos PostgreSQL temporal y aislada.

Se crea una base `yaku_test_<aleatorio>` en el mismo servidor configurado en
`.env` (o en TEST_DB_HOST/TEST_DB_PORT si se definen), se generan las tablas
desde los modelos y se elimina al finalizar la sesión de pytest. La base real
(DB_NAME) nunca se toca.
"""

import os
import sys
import uuid

import pytest
from dotenv import load_dotenv

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
load_dotenv(os.path.join(BACKEND_DIR, ".env"))

TEST_DB_NAME = f"yaku_test_{uuid.uuid4().hex[:8]}"
os.environ["DB_HOST"] = os.getenv("TEST_DB_HOST", os.environ["DB_HOST"])
os.environ["DB_PORT"] = os.getenv("TEST_DB_PORT", os.getenv("DB_PORT", "5432"))
# Debe fijarse ANTES de importar src.main.db.databaseConexion (crea el engine al importar).
os.environ["DB_NAME"] = TEST_DB_NAME
# Fuera de produccion no se consume telemetria ni corre el planificador.
os.environ["APP_ENV"] = "development"
# Clave propia de la sesion de tests: nunca se usa la de .env.
from cryptography.fernet import Fernet  # noqa: E402

os.environ["CREDENTIALS_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import URL  # noqa: E402


def _admin_engine():
    url = URL.create(
        "postgresql+psycopg2",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        database="postgres",
    )
    return create_engine(url, isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="session", autouse=True)
def test_database():
    admin = _admin_engine()
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))

    from src.main.db.databaseConexion import Base, engine
    import src.main.model.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(autouse=True)
def _aislar_efectos_secundarios(monkeypatch):
    """El backend dispara ML, websockets y publicaciones MQTT; los tests solo
    verifican persistencia y comandos. Nunca se conecta al broker real.

    Devuelve los eventos websocket emitidos por mqttServ."""
    from src.main.service import mqttServ
    import src.main.service.schedulerServ as scheduler
    import src.main.tasks.mqttSubscriberTask as mqtt_task

    eventos = []
    monkeypatch.setattr(mqttServ, "broadcast_ws_event", lambda p, uid: eventos.append((p, uid)))
    monkeypatch.setattr(scheduler, "check_ml_cooldown_and_irrigate", lambda db: None)
    monkeypatch.setattr(mqtt_task, "publish_mqtt_message", lambda *a, **k: None)

    def _broker_prohibido(*a, **k):
        raise AssertionError("Los tests no deben conectarse al broker MQTT real")

    monkeypatch.setattr(mqtt_task, "start_mqtt", _broker_prohibido)
    return eventos


@pytest.fixture()
def mqtt_publicado(monkeypatch, _aislar_efectos_secundarios):
    """Captura (topic, payload) de lo que el backend publicaría al broker."""
    import src.main.tasks.mqttSubscriberTask as mqtt_task

    publicados = []
    monkeypatch.setattr(
        mqtt_task, "publish_mqtt_message", lambda topic, payload, **k: publicados.append((topic, payload))
    )
    return publicados


@pytest.fixture()
def db(test_database):
    from src.main.db.databaseConexion import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
