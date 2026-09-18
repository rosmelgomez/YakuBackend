"""Contratos de datos de horarios fijos de riego (HU-17)."""

from datetime import datetime, time

from pydantic import BaseModel, Field


class HorarioRiegoCreate(BaseModel):
    id_asignacion: int
    hora_inicio: time
    duracion_segundos: int = Field(gt=0, le=3600)
    dias_semana: list[int] = Field(
        default_factory=list, description="0=lunes ... 6=domingo"
    )
    activo: bool = True


class HorarioRiegoUpdate(BaseModel):
    hora_inicio: time | None = None
    duracion_segundos: int | None = Field(default=None, gt=0, le=3600)
    dias_semana: list[int] | None = None
    activo: bool | None = None


class HorarioRiegoResponse(BaseModel):
    id: int
    id_asignacion: int
    id_usuario: int
    hora_inicio: time
    duracion_segundos: int
    dias_semana: list[int]
    activo: bool
    fecha_creacion: datetime | None = None
    ultima_ejecucion: datetime | None = None

    class Config:
        from_attributes = True
