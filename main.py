from fastapi import FastAPI
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.models.database import Base, engine
from src.tasks.mqtt_subscriber import start_mqtt, stop_mqtt
from src.routers.auth import router as auth_router
from src.routers.model import router as model_router
from src.routers.ml import router as ml_router
from src.routers.dispositivo import (
    router as dispositivo_router,
    legacy_router as legacy_bomba_router,
    singular_router as singular_dispositivo_router,
)
from src.routers.usuario import router as usuario_router
from src.routers.ubicacion import router as ubicacion_router
from src.routers.dashboard import router as dashboard_router

app = FastAPI(
    title="Yaku ESP32 API",
    version="1.0.0",
    description="API para gestionar datos de riego y predicciones basadas en un modelo de ML."
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


@app.on_event("startup")
def create_tables() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        start_mqtt()

        # Iniciar el planificador de riego programado en segundo plano
        from src.tasks.scheduler import start_scheduler
        start_scheduler()

        # Sembrar la base de datos si está vacía (no hay usuarios)
        from src.models.database import SessionLocal
        from src.models.models import usuarios
        db = SessionLocal()
        try:
            if db.query(usuarios).count() == 0:
                print("Base de datos vacía detectada. Sembrando datos...")
                from seed import ejecutar_semillas
                ejecutar_semillas()
        finally:
            db.close()
    except OperationalError:
        print("Advertencia: no se pudo conectar a PostgreSQL al iniciar; la API continuara sin crear tablas.")
    except SQLAlchemyError as exc:
        raise RuntimeError("Error al inicializar la base de datos") from exc


@app.on_event("shutdown")
def shutdown_mqtt_on_exit() -> None:
    stop_mqtt()
