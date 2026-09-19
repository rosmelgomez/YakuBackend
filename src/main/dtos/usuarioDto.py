"""Contratos de datos del módulo usuario."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.main.dtos.authDto import UserRegisterInput


class UsuarioResponseModel(BaseModel):
    id_usuario: int
    nombre: str
    apellido: Optional[str] = None
    correo: str
    id_rol: Optional[int] = None
    telefono: Optional[str] = None
    zona_horaria: Optional[str] = None
    verificado: bool
    estado: bool
    ultimo_acceso: Optional[datetime] = None
    fecha_registro: Optional[datetime] = None
    dni: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    direccion: Optional[str] = None
    fecha_modificacion: Optional[datetime] = None
    permisos: list[str] = []

    model_config = {"from_attributes": True}


class RolDetail(BaseModel):
    nombre: str

    model_config = {"from_attributes": True}


class UsuarioAdminResponse(BaseModel):
    id: int
    nombre: str
    apellido: Optional[str] = None
    correo: str
    id_rol: Optional[int] = None
    telefono: Optional[str] = None
    zona_horaria: Optional[str] = None
    verificado: bool
    estado: bool
    ultimo_acceso: Optional[datetime] = None
    fecha_registro: Optional[datetime] = None
    dni: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    direccion: Optional[str] = None
    fecha_modificacion: Optional[datetime] = None
    rol: Optional[RolDetail] = None

    model_config = {"from_attributes": True}


class AdminUserCreateInput(UserRegisterInput):
    id_rol: int = Field(ge=1, le=2)
