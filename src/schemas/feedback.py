from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_cultivo: Optional[int] = None
    comentario: Optional[str] = Field(default=None, max_length=1200)
    respuestas: list["FeedbackRespuestaCreate"] = Field(min_length=1)

    @field_validator("comentario")
    @classmethod
    def trim_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class FeedbackRespuestaCreate(BaseModel):
    id_pregunta: int
    calificacion: int = Field(ge=1, le=5)


class FeedbackPreguntaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pregunta: str = Field(min_length=8, max_length=500)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    orden: int = Field(default=0, ge=0)
    activo: bool = True

    @field_validator("pregunta", "descripcion")
    @classmethod
    def trim_question_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class FeedbackPreguntaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pregunta: Optional[str] = Field(default=None, min_length=8, max_length=500)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    orden: Optional[int] = Field(default=None, ge=0)
    activo: Optional[bool] = None

    @field_validator("pregunta", "descripcion")
    @classmethod
    def trim_update_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class FeedbackPreguntaResponse(BaseModel):
    id: int
    pregunta: str
    descripcion: Optional[str] = None
    orden: int
    activo: bool
    fecha_registro: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None


class FeedbackRespuestaResponse(BaseModel):
    id: int
    id_pregunta: int
    pregunta: str
    calificacion: int


class FeedbackResponse(BaseModel):
    id: int
    id_usuario: int
    id_cultivo: Optional[int] = None
    cultivo_nombre: Optional[str] = None
    modulo: str
    tipo: str
    calificacion: int
    mensaje: str
    estado: str
    fecha: datetime
    respuestas: list[FeedbackRespuestaResponse] = []
