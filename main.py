from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from starlette.types import ASGIApp, Scope, Receive, Send
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
from src.core.config import ALLOWED_ORIGINS, AUTO_CREATE_TABLES, IS_PRODUCTION

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        if AUTO_CREATE_TABLES:
            from src.db import models as _models  # noqa: F401

            Base.metadata.create_all(bind=engine)
        elif IS_PRODUCTION:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))

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


class SecurityAndCSRFMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers_dict = {}
        for k, v in scope.get("headers", []):
            headers_dict[k.lower()] = v

        method = scope.get("method", "GET")
        mutating = method in {"POST", "PUT", "PATCH", "DELETE"}

        cookie_bytes = headers_dict.get(b"cookie", b"")
        cookie_str = cookie_bytes.decode("utf-8") if cookie_bytes else ""
        cookies = {}
        if cookie_str:
            for item in cookie_str.split(";"):
                parts = item.split("=", 1)
                if len(parts) == 2:
                    cookies[parts[0].strip()] = parts[1].strip()

        cookie_authenticated = "access_token" in cookies or "refresh_token" in cookies
        x_bff_token = headers_dict.get(b"x-bff-token", b"").decode("utf-8") if b"x-bff-token" in headers_dict else ""

        if mutating and cookie_authenticated and not x_bff_token:
            origin = headers_dict.get(b"origin", b"").decode("utf-8").rstrip("/") if b"origin" in headers_dict else ""
            if not origin or origin not in ALLOWED_ORIGINS:
                await send({
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"application/json")]
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"detail": "Origen no autorizado"}'
                })
                return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers_list = message.get("headers", [])
                headers_map = {k.lower(): v for k, v in headers_list}
                
                headers_map[b"x-content-type-options"] = b"nosniff"
                headers_map[b"x-frame-options"] = b"DENY"
                headers_map[b"referrer-policy"] = b"no-referrer"
                headers_map[b"permissions-policy"] = b"camera=(), microphone=(), geolocation=()"
                headers_map[b"cache-control"] = b"no-store"
                if IS_PRODUCTION:
                    headers_map[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                
                message["headers"] = list(headers_map.items())
            await send(message)

        await self.app(scope, receive, send_wrapper)

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


