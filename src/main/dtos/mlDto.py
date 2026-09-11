"""Contratos de datos del módulo ml."""

from pydantic import BaseModel


class PrediccionRiegoModel(BaseModel):
    humedad_suelo: float
    humedad_ambiente: float
    temperatura_ambiente: float
    temperatura_suelo: float


class ModelInfo(BaseModel):
    id_modelo: int
    nombre_modelo: str
    algoritmo: str
    descripcion: str | None = None
    version: str | None = None
    precision_modelo: float | None = None
    activo: bool = False


class ModelSelect(BaseModel):
    model_name: str


class ModelSelectionResponse(BaseModel):
    status: str
    selected: str
    model_id: int


class DbTrainingRequest(BaseModel):
    crop: str = "tomato"
    algorithm: str = "rf"
