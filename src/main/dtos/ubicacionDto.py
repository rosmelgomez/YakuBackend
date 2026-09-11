"""Contratos de datos del módulo ubicacion."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from src.main.core.waterSource import normalize_source_type


class RegionResponseModel(BaseModel):
    id: int
    nombre: str

    model_config = {"from_attributes": True}


class ProvinciaResponseModel(BaseModel):
    id: int
    id_region: int
    nombre: str

    model_config = {"from_attributes": True}


class DistritoResponseModel(BaseModel):
    id: int
    id_provincia: int
    nombre: str

    model_config = {"from_attributes": True}


class FuenteAguaResponseModel(BaseModel):
    id: int
    id_usuario: int
    nombre: str
    tipo: str
    capacidad_litros: Optional[float] = None
    capacidad_m3: Optional[float] = None
    altura_tanque_cm: Optional[float] = None
    altura_seguridad_cm: Optional[float] = None
    fecha_registro: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CultivoResponseModel(BaseModel):
    id_cultivo: int
    id_usuario: int
    id_planta: Optional[int] = None
    id_fuente_agua: Optional[int] = None
    id_distrito: Optional[int] = None
    lugar: Optional[str] = None
    nombre_planta: str
    etapa_crecimiento: Optional[str] = None
    area_m2: Optional[float] = None
    fecha_siembra: Optional[object] = None
    estado: str
    fecha_registro: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RegionCreate(BaseModel):
    nombre: str


class ProvinciaCreate(BaseModel):
    id_region: int
    nombre: str


class DistritoCreate(BaseModel):
    id_provincia: int
    nombre: str


class CultivoCreate(BaseModel):
    id_planta: Optional[int] = None
    id_fuente_agua: Optional[int] = None
    id_distrito: Optional[int] = None
    lugar: Optional[str] = None
    nombre_planta: str
    etapa_crecimiento: Optional[str] = None
    area_m2: Optional[float] = None
    fecha_siembra: Optional[str] = None


class FuenteAguaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    tipo: str
    capacidad_litros: Optional[float] = Field(default=None, gt=0, le=99999999.99, allow_inf_nan=False)
    altura_tanque_cm: Optional[float] = Field(default=None, gt=0, le=9999.99, allow_inf_nan=False)
    altura_seguridad_cm: Optional[float] = Field(default=None, ge=0, le=9999.99, allow_inf_nan=False)

    @field_validator("tipo")
    @classmethod
    def normalize_type(cls, value):
        return normalize_source_type(value)

    @field_validator("nombre")
    @classmethod
    def nonempty_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("El nombre es obligatorio.")
        return value

    @model_validator(mode="after")
    def validate_dimensions(self):
        if self.tipo == "conexion_directa":
            self.capacidad_litros = None
            self.altura_tanque_cm = None
            self.altura_seguridad_cm = None
        else:
            if self.capacidad_litros is None or self.altura_tanque_cm is None:
                raise ValueError("El tanque requiere capacidad en litros y altura en cm.")
            if self.altura_seguridad_cm is None:
                self.altura_seguridad_cm = 10.0
            if self.altura_seguridad_cm >= self.altura_tanque_cm:
                raise ValueError("La altura de seguridad debe ser menor que la altura del tanque.")
        return self


class CultivoAdminResponse(BaseModel):
    id: int
    id_cultivo: int
    id_usuario: int
    id_planta: Optional[int] = None
    id_fuente_agua: Optional[int] = None
    id_distrito: Optional[int] = None
    lugar: Optional[str] = None
    nombre_planta: str
    etapa_crecimiento: Optional[str] = None
    area_m2: Optional[float] = None
    fecha_siembra: Optional[object] = None
    estado: str
    fecha_registro: Optional[datetime] = None

    model_config = {"from_attributes": True}
