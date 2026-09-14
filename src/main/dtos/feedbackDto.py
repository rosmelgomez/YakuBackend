"""Contratos de datos del módulo feedback."""

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
    calificacion: Optional[int] = Field(default=None, ge=1, le=5)
    respuesta_texto: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("respuesta_texto")
    @classmethod
    def trim_respuesta_texto(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class FeedbackPreguntaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pregunta: str = Field(min_length=3, max_length=500)
    tipo: str = Field(default="rating", pattern="^(rating|text|select)$")
    obligatoria: bool = True
    opciones: Optional[list[str]] = None
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

    pregunta: Optional[str] = Field(default=None, min_length=3, max_length=500)
    tipo: Optional[str] = Field(default=None, pattern="^(rating|text|select)$")
    obligatoria: Optional[bool] = None
    opciones: Optional[list[str]] = None
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
    tipo: str = "rating"
    obligatoria: bool = True
    opciones: Optional[list[str]] = None
    descripcion: Optional[str] = None
    orden: int
    activo: bool
    fecha_registro: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None


class FeedbackRespuestaResponse(BaseModel):
    id: int
    id_pregunta: int
    pregunta: str
    tipo: Optional[str] = "rating"
    calificacion: Optional[int] = None
    respuesta_texto: Optional[str] = None


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


class FeedbackRespuestaTextoItem(BaseModel):
    texto: str
    fecha: Optional[datetime] = None
    calificacion_general: Optional[int] = None


class FeedbackPreguntaKpi(BaseModel):
    id_pregunta: int
    pregunta: str
    tipo: str
    obligatoria: bool
    activo: bool
    orden: int
    total_respuestas: int
    tasa_respuesta_porcentaje: float
    promedio_calificacion: Optional[float] = None
    distribucion_calificacion: Optional[dict[str, int]] = None
    porcentaje_positivas: Optional[float] = None
    distribucion_opciones: Optional[dict[str, int]] = None
    opcion_mas_votada: Optional[str] = None
    longitud_promedio: Optional[float] = None
    ultimas_respuestas_texto: Optional[list[FeedbackRespuestaTextoItem]] = None


class FeedbackKpisResponse(BaseModel):
    total_feedbacks: int
    promedio_general: float
    preguntas_activas: int
    preguntas_totales: int
    tasa_completitud_promedio: float
    preguntas_kpis: list[FeedbackPreguntaKpi]
