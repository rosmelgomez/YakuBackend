"""Contratos de datos de permisos granulares (HU-31)."""

from pydantic import BaseModel


class PermisoResponse(BaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None = None

    class Config:
        from_attributes = True


class PermisosUsuarioUpdate(BaseModel):
    codigos: list[str]
