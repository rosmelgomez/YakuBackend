"""Contratos de datos de horarios de riego (HU-17).

Un horario define CUANDO se le permite al riego automatico por IA evaluar y
regar -- nunca dispara un riego por si mismo. Puede ser:
- De franja fija: el usuario define un rango "de hora a hora" (hora_inicio /
  hora_fin, opcionalmente dias_semana). Dentro de esa ventana (soporta cruzar
  medianoche, y hora_inicio == hora_fin se interpreta como "todo el dia"), la
  IA puede evaluar cooldown/sensores y regar si corresponde; fuera de ella,
  no se evalua nada.
- "Siempre activo" (`siempre_activo=True`): sin franja horaria; la IA puede
  evaluar en cualquier momento del dia.
"""

from datetime import datetime, time

from pydantic import BaseModel, Field, model_validator


class HorarioRiegoCreate(BaseModel):
    id_asignacion: int
    siempre_activo: bool = False
    hora_inicio: time | None = None
    hora_fin: time | None = None
    dias_semana: list[int] = Field(
        default_factory=list, description="0=lunes ... 6=domingo"
    )
    activo: bool = True

    @model_validator(mode="after")
    def _validar_franja(self):
        if not self.siempre_activo and (self.hora_inicio is None or self.hora_fin is None):
            raise ValueError(
                "Debe indicar hora_inicio y hora_fin, o marcar siempre_activo."
            )
        return self


class HorarioRiegoUpdate(BaseModel):
    siempre_activo: bool | None = None
    hora_inicio: time | None = None
    hora_fin: time | None = None
    dias_semana: list[int] | None = None
    activo: bool | None = None


class HorarioRiegoResponse(BaseModel):
    id: int
    id_asignacion: int
    id_usuario: int
    siempre_activo: bool
    hora_inicio: time | None = None
    hora_fin: time | None = None
    duracion_segundos: int | None = None
    dias_semana: list[int]
    activo: bool
    fecha_creacion: datetime | None = None
    ultima_ejecucion: datetime | None = None

    class Config:
        from_attributes = True
