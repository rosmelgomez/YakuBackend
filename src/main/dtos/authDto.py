"""Contratos de datos del módulo auth."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class AuthModel(BaseModel):
    usuario: str
    contrasena: str


class UsuarioTokenModel(BaseModel):
    id_usuario: int
    nombre: str
    correo: str
    id_rol: int | None = None


class TokenResponseModel(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UsuarioTokenModel


class LoginResponseModel(BaseModel):
    status: str = "ok"
    message: str = "Inicio de sesión exitoso"


class UserRegisterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=2, max_length=100)
    apellido: Optional[str] = Field(default=None, max_length=100)
    correo: EmailStr
    contrasena: str = Field(min_length=10, max_length=128)
    telefono: Optional[str] = Field(default=None, max_length=20)
    zona_horaria: Optional[str] = Field(default="America/Lima", max_length=50)
    dni: Optional[str] = Field(default=None, max_length=20)
    fecha_nacimiento: Optional[date] = None
    direccion: Optional[str] = Field(default=None, max_length=255)

    @field_validator("contrasena")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(char.islower() for char in value) or not any(
            char.isupper() for char in value
        ):
            raise ValueError("La contrasena debe incluir mayusculas y minusculas")
        if not any(char.isdigit() for char in value):
            raise ValueError("La contrasena debe incluir al menos un numero")
        return value


class UserRegisterResponse(BaseModel):
    success: bool
    message: str
    userId: int
    verificationToken: Optional[str] = None


class VerifyCredentialsInput(BaseModel):
    correo: Optional[str] = None
    contrasena: Optional[str] = None
    token: Optional[str] = None


class VerifyTokenInput(BaseModel):
    token: str
    correo: Optional[EmailStr] = None


class ResendCodeInput(BaseModel):
    correo: EmailStr


class ResendCodeResponse(BaseModel):
    success: bool
    message: str


class UserVerifyResponse(BaseModel):
    id: str
    name: str
    email: str
    rol: str
    permisos: list[str] = []


class UserUpdateInput(BaseModel):
    nombre: str = Field(min_length=2, max_length=100)
    apellido: str | None = Field(default=None, max_length=100)
    correo: EmailStr
    telefono: str | None = Field(default=None, max_length=20)
    zona_horaria: str | None = Field(default="America/Lima", max_length=50)
    dni: str | None = Field(default=None, max_length=20)
    fecha_nacimiento: date | None = None
    direccion: str | None = Field(default=None, max_length=255)
    contrasena: str | None = Field(default=None, min_length=10, max_length=128)

    @field_validator("contrasena")
    @classmethod
    def validate_optional_password(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not any(char.islower() for char in value) or not any(
            char.isupper() for char in value
        ):
            raise ValueError("La contrasena debe incluir mayusculas y minusculas")
        if not any(char.isdigit() for char in value):
            raise ValueError("La contrasena debe incluir al menos un numero")
        return value


class PasswordResetRequestInput(BaseModel):
    correo: EmailStr


class PasswordResetConfirmInput(BaseModel):
    correo: EmailStr
    codigo: str = Field(min_length=6, max_length=6)
    nueva_contrasena: str = Field(min_length=10, max_length=128)

    @field_validator("nueva_contrasena")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(char.islower() for char in value) or not any(
            char.isupper() for char in value
        ):
            raise ValueError("La contrasena debe incluir mayusculas y minusculas")
        if not any(char.isdigit() for char in value):
            raise ValueError("La contrasena debe incluir al menos un numero")
        return value


class PasswordResetResponse(BaseModel):
    success: bool
    message: str

