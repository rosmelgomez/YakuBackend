from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FirmwareSegment(BaseModel):
    nombre: str
    direccion: int = Field(ge=0)
    sha256: str
    tamano: int = Field(ge=1)


class FirmwareVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: str
    chip: str
    tipo_dispositivo: str
    descripcion: str | None = None
    publicado: bool
    descontinuado: bool = False
    ubicacion_archivo: str | None = None
    manifiesto: dict[str, Any]
    archivos_faltantes: list[str] = Field(default_factory=list)
    fecha_registro: datetime
    fecha_descontinuado: datetime | None = None


class FirmwareInstallationCreate(BaseModel):
    id_firmware: int
    id_dispositivo: int
    chip_detectado: str | None = None
    mac_detectada: str | None = None


class FirmwareInstallationUpdate(BaseModel):
    estado: Literal["iniciada", "instalando", "completada", "error", "cancelada"]
    progreso: int = Field(ge=0, le=100)
    mensaje: str | None = Field(default=None, max_length=1000)


class FirmwareInstallationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_firmware: int
    id_dispositivo: int
    id_administrador: int
    chip_detectado: str | None = None
    mac_detectada: str | None = None
    estado: str
    progreso: int
    mensaje: str | None = None
    fecha_inicio: datetime
    fecha_fin: datetime | None = None
