"""Contratos de datos del módulo planta."""

from typing import List, Optional

from pydantic import BaseModel


class UmbralPlantaSchema(BaseModel):
    id_tipo_metrica: int
    valor_minimo: Optional[float] = None
    valor_maximo: Optional[float] = None


class PlantaCreate(BaseModel):
    nombre: str
    tipo: Optional[str] = None
    descripcion: Optional[str] = None
    umbrales: Optional[List[UmbralPlantaSchema]] = None


class PlantaResponseModel(BaseModel):
    id: int
    nombre: str
    tipo: Optional[str] = None
    descripcion: Optional[str] = None
    umbrales: Optional[List[UmbralPlantaSchema]] = None

    model_config = {"from_attributes": True}
