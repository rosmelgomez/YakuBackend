"""Contratos de datos del historial de logs del sistema."""

from datetime import datetime

from pydantic import BaseModel


class LogSistemaResponse(BaseModel):
    id: int
    id_usuario: int | None = None
    accion: str
    modulo: str | None = None
    descripcion: str | None = None
    fecha: datetime | None = None

    class Config:
        from_attributes = True
