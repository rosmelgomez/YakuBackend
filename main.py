from fastapi import FastAPI
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.Model.conexion import Base, engine
from src.MQTT.mqtt_subscriber import start_mqtt, stop_mqtt
from src.Router.model_router import router as model_router
from src.Router.ml_router import router as ml_router

app = FastAPI(title="Yaku ESP32 API", version="1.0.0", description="API para gestionar datos de riego y predicciones basadas en un modelo de ML.")
app.include_router(model_router)
app.include_router(ml_router)


@app.on_event("startup")
def create_tables() -> None:
	try:
		Base.metadata.create_all(bind=engine)
		start_mqtt()
	except OperationalError:
		print("Advertencia: no se pudo conectar a PostgreSQL al iniciar; la API continuara sin crear tablas.")
	except SQLAlchemyError as exc:
		raise RuntimeError("Error al inicializar la base de datos") from exc


@app.on_event("shutdown")
def shutdown_mqtt_on_exit() -> None:
	stop_mqtt()
