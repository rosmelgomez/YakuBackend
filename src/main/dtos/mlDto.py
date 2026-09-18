"""Contratos de datos del módulo ml."""

from datetime import datetime

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
    importancias_features: dict[str, float] | None = None


class PrediccionHistorialItem(BaseModel):
    id_prediccion: int
    id_cultivo: int | None = None
    variables_entrada: dict
    recomendacion: str | None = None
    probabilidad: float | None = None
    accion_ejecutada: bool | None = None
    fuente_accion: str | None = None
    fecha: datetime | None = None

    class Config:
        from_attributes = True


class ModelSelect(BaseModel):
    model_name: str


class ModelSelectionResponse(BaseModel):
    status: str
    selected: str
    model_id: int


class DbTrainingRequest(BaseModel):
    crop: str = "tomato"
    algorithm: str = "rf"
