"""Contratos de datos del módulo common."""

from pydantic import BaseModel


class UserBriefResponse(BaseModel):
    nombre: str

    model_config = {"from_attributes": True}


class CropBriefResponse(BaseModel):
    nombre_planta: str

    model_config = {"from_attributes": True}
