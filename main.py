from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.db.database import Base, engine
from src.tasks.mqtt_subscriber import start_mqtt, stop_mqtt
from src.api.routers.auth import router as auth_router
from src.api.routers.model import router as model_router
from src.api.routers.ml import router as ml_router
from src.api.routers.dispositivo import (
    router as dispositivo_router,
    legacy_router as legacy_bomba_router,
    singular_router as singular_dispositivo_router,
)
from src.api.routers.usuario import router as usuario_router
from src.api.routers.ubicacion import router as ubicacion_router
from src.api.routers.dashboard import router as dashboard_router
from src.api.routers.backup import router as backup_router
from src.api.routers.planta import router as planta_router
from src.api.routers.almacen import router as almacen_router
from src.api.routers.webpush import router as webpush_router
from src.api.routers.firmware import router as firmware_router
from src.api.routers.feedback import router as feedback_router
from src.services.notifications.websocket_manager import manager
from src.core.bff_tokens import decode_bff_token
from src.core.config import ALLOWED_ORIGINS, AUTO_CREATE_TABLES, IS_PRODUCTION
from src.core.middleware import SecurityAndCSRFMiddleware

logger = logging.getLogger(__name__)


FEEDBACK_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS feedback_agricultores (
        id SERIAL PRIMARY KEY,
        id_usuario INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        id_cultivo INTEGER REFERENCES cultivos(id) ON DELETE SET NULL,
        modulo VARCHAR(50) NOT NULL,
        tipo VARCHAR(30) NOT NULL,
        calificacion INTEGER NOT NULL,
        mensaje TEXT NOT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'nuevo',
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_feedback_calificacion CHECK (calificacion BETWEEN 1 AND 5)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_feedback_agricultores_id_usuario ON feedback_agricultores(id_usuario)",
    "CREATE INDEX IF NOT EXISTS ix_feedback_agricultores_id_cultivo ON feedback_agricultores(id_cultivo)",
    """
    CREATE TABLE IF NOT EXISTS feedback_preguntas (
        id SERIAL PRIMARY KEY,
        pregunta TEXT NOT NULL,
        descripcion TEXT,
        orden INTEGER NOT NULL DEFAULT 0,
        activo BOOLEAN NOT NULL DEFAULT TRUE,
        fecha_registro TIMESTAMP NOT NULL DEFAULT NOW(),
        actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_respuestas (
        id SERIAL PRIMARY KEY,
        id_feedback INTEGER NOT NULL REFERENCES feedback_agricultores(id) ON DELETE CASCADE,
        id_pregunta INTEGER NOT NULL REFERENCES feedback_preguntas(id) ON DELETE RESTRICT,
        calificacion INTEGER NOT NULL,
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_feedback_respuesta_calificacion CHECK (calificacion BETWEEN 1 AND 5),
        CONSTRAINT uq_feedback_respuesta_pregunta UNIQUE (id_feedback, id_pregunta)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_feedback_respuestas_id_feedback ON feedback_respuestas(id_feedback)",
    "CREATE INDEX IF NOT EXISTS ix_feedback_respuestas_id_pregunta ON feedback_respuestas(id_pregunta)",
    """
    INSERT INTO feedback_preguntas (pregunta, orden, activo)
    SELECT pregunta, orden, TRUE
    FROM (
        VALUES
            ('Te parecio facil usar y entender el sistema Yaku?', 1),
            ('Fueron claras las recomendaciones y alertas del sistema?', 2),
            ('Consideras utiles o adecuadas las recomendaciones de riego?', 3),
            ('La interaccion con el sistema se realizo sin dificultades?', 4),
            ('Estas satisfecho con la experiencia general del sistema?', 5)
    ) AS defaults(pregunta, orden)
    WHERE NOT EXISTS (SELECT 1 FROM feedback_preguntas)
    """,
)


IRRIGATION_EXECUTION_SCHEMA_STATEMENTS = (
    "ALTER TABLE riego ADD COLUMN IF NOT EXISTS segundos_acumulados INT DEFAULT 0",
    "ALTER TABLE riego ADD COLUMN IF NOT EXISTS fecha_inicio TIMESTAMP",
    "ALTER TABLE riego ADD COLUMN IF NOT EXISTS fecha_fin TIMESTAMP",
    """
    CREATE TABLE IF NOT EXISTS ejecuciones_riego (
        id SERIAL PRIMARY KEY,
        id_riego BIGINT NOT NULL REFERENCES riego(id) ON DELETE CASCADE,
        fecha_inicio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_fin TIMESTAMP,
        distancia_inicial_cm NUMERIC(6,2),
        distancia_final_cm NUMERIC(6,2),
        duracion_segundos INT DEFAULT 0,
        cantidad_agua_litros NUMERIC(10,2) DEFAULT 0.0,
        motivo_cierre VARCHAR(50)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ejecuciones_riego_riego ON ejecuciones_riego(id_riego)",
    "CREATE INDEX IF NOT EXISTS idx_ejecuciones_riego_fecha ON ejecuciones_riego(fecha_inicio DESC)",
)


def run_migrations() -> None:
    import glob
    import os
    import re
    migrations_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "migrations"))
    if not os.path.exists(migrations_dir):
        logger.warning(f"Directorio de migraciones no encontrado: {migrations_dir}")
        return

    sql_pattern = os.path.join(migrations_dir, "*.sql")
    migration_files = sorted(glob.glob(sql_pattern))
    logger.info(f"Se encontraron {len(migration_files)} archivos de migración SQL para ejecutar.")

    with engine.begin() as conn:
        for migration_file in migration_files:
            logger.info(f"Ejecutando migración SQL: {os.path.basename(migration_file)}...")
            try:
                with open(migration_file, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as read_err:
                logger.error(f"Error al leer el archivo SQL {migration_file}: {read_err}")
                continue

            # Eliminar comentarios
            content = re.sub(r'--.*', '', content)
            
            # Separar comandos por punto y coma (;) respetando el fin de línea
            statements = []
            current_stmt = []
            for line in content.splitlines():
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                current_stmt.append(line)
                if line_stripped.endswith(";"):
                    statements.append("\n".join(current_stmt))
                    current_stmt = []
                    
            if current_stmt:
                stmt = "\n".join(current_stmt).strip()
                if stmt:
                    statements.append(stmt)

            cursor = conn.connection.cursor()
            try:
                for stmt in statements:
                    stmt_clean = stmt.strip()
                    if stmt_clean:
                        cursor.execute(stmt_clean)
            except Exception as stmt_err:
                logger.error(f"Error en comando SQL de {os.path.basename(migration_file)}: {stmt_err}")
                raise stmt_err
            finally:
                cursor.close()
    logger.info("Migraciones SQL ejecutadas con éxito.")


def ensure_feedback_schema() -> None:
    with engine.begin() as connection:
        for statement in FEEDBACK_SCHEMA_STATEMENTS:
            connection.execute(text(statement))
    logger.info("Esquema de feedback verificado")


def ensure_irrigation_execution_schema() -> None:
    with engine.begin() as connection:
        for statement in IRRIGATION_EXECUTION_SCHEMA_STATEMENTS:
            connection.execute(text(statement))
    logger.info("Esquema de ejecuciones de riego verificado")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        if AUTO_CREATE_TABLES:
            from src.db import models as _models  # noqa: F401

            Base.metadata.create_all(bind=engine)
        elif IS_PRODUCTION:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))

        run_migrations()
        ensure_irrigation_execution_schema()
        ensure_feedback_schema()

        if not IS_PRODUCTION:
            from src.db.database import SessionLocal
            from src.db.models import usuarios

            db = SessionLocal()
            try:
                db_empty = db.query(usuarios).count() == 0
            finally:
                db.close()
            if db_empty:
                logger.info("Base de datos vacía detectada; cargando datos de desarrollo")
                from seed import ejecutar_semillas
                ejecutar_semillas()

        # Sincronización de firmwares en disco con la BD
        from src.db.database import SessionLocal
        from src.api.routers.firmware import sincronizar_firmwares_disco
        db = SessionLocal()
        try:
            sincronizar_firmwares_disco(db)
        except Exception as e:
            logger.error(f"Error durante la sincronización de firmwares: {e}")
        finally:
            db.close()

        start_mqtt()
        from src.tasks.scheduler import start_scheduler
        start_scheduler()
    except OperationalError as exc:
        if IS_PRODUCTION:
            raise RuntimeError("PostgreSQL no está disponible durante el arranque") from exc
        logger.warning("PostgreSQL no está disponible; los servicios dependientes quedan deshabilitados")
    except SQLAlchemyError as exc:
        raise RuntimeError("Error al inicializar la base de datos") from exc

    try:
        yield
    finally:
        stop_mqtt()

app = FastAPI(
    title="Yaku ESP32 API",
    version="1.0.0",
    description="API para gestionar datos de riego y predicciones basadas en un modelo de ML.",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)


app.add_middleware(SecurityAndCSRFMiddleware)

app.include_router(auth_router)
app.include_router(legacy_bomba_router)
app.include_router(model_router)
app.include_router(ml_router)
app.include_router(dispositivo_router)
app.include_router(singular_dispositivo_router)
app.include_router(usuario_router)
app.include_router(ubicacion_router)
app.include_router(dashboard_router)
app.include_router(backup_router)
app.include_router(planta_router)
app.include_router(almacen_router)
app.include_router(webpush_router)
app.include_router(firmware_router)
app.include_router(feedback_router)


@app.get("/health/live", include_in_schema=False)
def health_live():
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def health_ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}



@app.websocket("/ws/alertas")
async def websocket_endpoint(websocket: WebSocket):
    origin = (websocket.headers.get("origin") or "").rstrip("/")
    if ALLOWED_ORIGINS and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008, reason="Origen no autorizado")
        return
    ticket = websocket.query_params.get("ticket", "")
    try:
        payload = decode_bff_token(ticket, audience="yaku-websocket")
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        await websocket.close(code=1008, reason="Ticket invalido")
        return

    from src.db.database import SessionLocal
    from src.db.models import usuarios

    db = SessionLocal()
    try:
        user = db.query(usuarios).filter(
            usuarios.id_usuario == user_id,
            usuarios.estado.is_(True),
        ).first()
        if not user:
            await websocket.close(code=1008, reason="Usuario no autorizado")
            return
        is_admin = user.id_rol == 1
    finally:
        db.close()

    await manager.connect(websocket, user_id=user_id, is_admin=is_admin)
    try:
        while True:
            # Mantener la conexión activa esperando cualquier trama (ej. ping)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("Error inesperado en WebSocket")
        manager.disconnect(websocket)
