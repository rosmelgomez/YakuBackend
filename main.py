from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
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
from src.services.notifications.websocket_manager import manager
from src.core.bff_tokens import decode_bff_token
from src.core.config import ALLOWED_ORIGINS, IS_PRODUCTION

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        if IS_PRODUCTION:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        else:
            Base.metadata.create_all(bind=engine)
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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def csrf_origin_guard(request: Request, call_next):
    mutating = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    cookie_authenticated = "access_token" in request.cookies or "refresh_token" in request.cookies
    if mutating and cookie_authenticated and not request.headers.get("X-BFF-Token"):
        origin = (request.headers.get("Origin") or "").rstrip("/")
        if not origin or origin not in ALLOWED_ORIGINS:
            return JSONResponse(status_code=403, content={"detail": "Origen no autorizado"})
    return await call_next(request)

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


