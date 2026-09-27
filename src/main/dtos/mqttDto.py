"""Contratos de datos de la configuración administrable del broker MQTT (HU-08)."""

from datetime import datetime

from pydantic import BaseModel, Field


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


# Usuario MQTT: mismo juego de caracteres que un client_id del firmware, sin
# espacios ni comodines de topico (#, +) que el broker podria interpretar.
_PATRON_USUARIO_MQTT = r"^[A-Za-z0-9_.@:\-]+$"


class CredencialDispositivoGuardar(BaseModel):
    username: str = Field(min_length=3, max_length=150, pattern=_PATRON_USUARIO_MQTT)
    # Obligatoria al registrar; al modificar, vacia conserva la clave guardada.
    password: str | None = Field(default=None, min_length=8, max_length=100)


class CredencialDispositivoResponse(BaseModel):
    """Estado de la credencial de un dispositivo. La clave nunca se devuelve
    aqui: solo viaja al ESP32 dentro del provisionamiento de firmware."""

    id_dispositivo: int
    nombre: str
    client_id_mqtt: str | None = None
    tipo: str | None = None
    estado: str | None = None
    username: str | None = None
    tiene_credencial: bool
    fecha_actualizacion: datetime | None = None


class MqttEstadoResponse(BaseModel):
    """Estado real de la conexion del backend con el broker MQTT."""

    # conectando | conectado | error | desconectado
    estado: str
    mensaje: str | None = None
    # Codigo CONNACK (4 = usuario/clave incorrectos, 5 = no autorizado) o de desconexion.
    codigo: int | None = None
    desde: datetime | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    tls: bool = True
