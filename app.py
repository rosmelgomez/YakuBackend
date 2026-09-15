import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from src.main.controller.apiAlmacen import router as almacen_router
from src.main.controller.apiAuth import router as auth_router
from src.main.controller.apiBackup import router as backup_router
from src.main.controller.apiDashboard import router as dashboard_router
from src.main.controller.apiDispositivo import legacy_router as legacy_bomba_router
from src.main.controller.apiDispositivo import router as dispositivo_router
from src.main.controller.apiDispositivo import (
    singular_router as singular_dispositivo_router,
)
from src.main.controller.apiFeedback import router as feedback_router
from src.main.controller.apiFirmware import router as firmware_router
from src.main.controller.apiMl import router as ml_router
from src.main.controller.apiNotificaciones import router as notificaciones_router
from src.main.controller.apiPlanta import router as planta_router
from src.main.controller.apiSistema import router as sistema_router
from src.main.controller.apiTelemetria import router as model_router
from src.main.controller.apiUbicacion import router as ubicacion_router
from src.main.controller.apiUsuario import router as usuario_router
from src.main.controller.apiWebpush import router as webpush_router
from src.main.core.application import lifespan
from src.main.core.middleware import SecurityAndCSRFMiddleware
from src.main.core.yakuConfig import ALLOWED_ORIGINS, IS_PRODUCTION

logger = logging.getLogger(__name__)


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(notificaciones_router)


app.include_router(sistema_router)
