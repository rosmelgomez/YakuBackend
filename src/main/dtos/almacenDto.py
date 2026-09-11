"""Contratos de datos del módulo almacen."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from src.main.dtos.ubicacionDto import DistritoResponseModel


class AlmacenCreate(BaseModel):
    nombre: str
    id_distrito: Optional[int] = None
    direccion: Optional[str] = None


class AlmacenResponseModel(BaseModel):
    id: int
    nombre: str
    id_distrito: Optional[int] = None
    distrito: Optional[DistritoResponseModel] = None
    direccion: Optional[str] = None
    fecha_registro: Optional[datetime] = None

    model_config = {"from_attributes": True}
