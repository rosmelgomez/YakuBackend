from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HumedadSueloModel(BaseModel):
    sensor: str
    valor: float
    porcentaje: float
    fecha: Optional[datetime] = None


class HumedadAmbienteModel(BaseModel):
    sensor: str
    valor: float
    porcentaje: float
    fecha: Optional[datetime] = None


class TemperaturaAmbienteModel(BaseModel):
    sensor: str
    valor: float
    temperatura: float
    fecha: Optional[datetime] = None


class TemperaturaSueloModel(BaseModel):
    sensor: str
    valor: float
    temperatura: float
    fecha: Optional[datetime] = None


class ControlAguaModel(BaseModel):
    sensor: str = "HC-SR04"
    distancia_cm: float
    altura_referencia_cm: float
    nivel_agua_cm: Optional[float] = None
    porcentaje_nivel: Optional[float] = None
    estado_bomba: str
    fecha: Optional[datetime] = None


class RiegoDatosModel(BaseModel):
    humedad_suelo: HumedadSueloModel
    humedad_ambiente: HumedadAmbienteModel
    temperatura_ambiente: TemperaturaAmbienteModel
    temperatura_suelo: TemperaturaSueloModel


class PrediccionRiegoModel(BaseModel):
    humedad_suelo: float
    humedad_ambiente: float
    temperatura_ambiente: float
    temperatura_suelo: float