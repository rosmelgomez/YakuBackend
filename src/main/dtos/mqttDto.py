"""Contratos de datos de la configuración administrable del broker MQTT (HU-08)."""

from datetime import datetime

from pydantic import BaseModel


class MqttConfigUpdate(BaseModel):
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    usar_tls: bool = True


class MqttConfigResponse(BaseModel):
    id: int
    host: str
    port: int
    username: str | None = None
    usar_tls: bool
    fecha_actualizacion: datetime | None = None

    class Config:
        from_attributes = True
