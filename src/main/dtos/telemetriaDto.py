"""Contratos de datos del módulo telemetria."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class HumedadSueloModel(BaseModel):
    id_asignacion: int
    valor: Optional[float] = None
    porcentaje: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class HumedadAmbienteModel(BaseModel):
    id_asignacion: int
    valor: Optional[float] = None
    porcentaje: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class TemperaturaAmbienteModel(BaseModel):
    id_asignacion: int
    valor: Optional[float] = None
    temperatura: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class TemperaturaSueloModel(BaseModel):
    id_asignacion: int
    valor: Optional[float] = None
    temperatura: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class TelemetriaTanqueModel(BaseModel):
    id_asignacion: int
    distancia_cm: Optional[float] = Field(default=None, allow_inf_nan=False)
    metodo_medicion: Optional[Literal["proximidad", "flujometro"]] = None
    estado_bomba: str
    valvula_abierta: Optional[bool] = None
    motivo_cierre: Optional[str] = None
    duracion_objetivo_seg: Optional[int] = None
    tiempo_ejecutado_seg: Optional[int] = None
    tiempo_restante_seg: Optional[int] = None
    litros_riego: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    litros_acumulados: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    caudal_l_min: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    pulsos_riego: Optional[int] = Field(default=None, ge=0)
    pulsos_por_litro: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    # Sesion 'riego' que abrio el ciclo del equipo (firmware de flujo >= 1.0.12).
    id_riego: Optional[int] = Field(default=None, gt=0)
    fecha: Optional[datetime] = None


class RiegoDatosModel(BaseModel):
    humedad_suelo: HumedadSueloModel
    humedad_ambiente: HumedadAmbienteModel
    temperatura_ambiente: TemperaturaAmbienteModel
    temperatura_suelo: TemperaturaSueloModel
