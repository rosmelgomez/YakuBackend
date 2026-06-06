
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HumedadSueloModel(BaseModel):
    sensor: str
    valor: float
    porcentaje: float
    fecha: Optional[datetime] = None


class HumedadAmbienteModel(BaseModel):
    sensor: str
    valor: float
    porcentaje: float
    fecha: Optional[datetime] = None


class TemperaturaAmbienteModel(BaseModel):
    sensor: str
    valor: float
    temperatura: float
    fecha: Optional[datetime] = None


class TemperaturaSueloModel(BaseModel):
    sensor: str
    valor: float
    temperatura: float
    fecha: Optional[datetime] = None


class ControlAguaModel(BaseModel):
    sensor: str = "HC-SR04"
    distancia_cm: float
    altura_referencia_cm: float
    nivel_agua_cm: Optional[float] = None
    porcentaje_nivel: Optional[float] = None
    estado_bomba: str
    fecha: Optional[datetime] = None


class RiegoDatosModel(BaseModel):
    humedad_suelo: HumedadSueloModel
    humedad_ambiente: HumedadAmbienteModel
    temperatura_ambiente: TemperaturaAmbienteModel
    temperatura_suelo: TemperaturaSueloModel


class PrediccionRiegoModel(BaseModel):
    humedad_suelo: float
    humedad_ambiente: float
    temperatura_ambiente: float
    temperatura_suelo: float


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


class BombaControlResponseModel(BaseModel):
    status: str
    accion: str
    topic: str

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class HumedadSueloModel(BaseModel):
    sensor: str
    id_sensor: Optional[int] = None
    valor: Optional[float] = None
    porcentaje: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class HumedadAmbienteModel(BaseModel):
    sensor: str
    id_sensor: Optional[int] = None
    valor: Optional[float] = None
    porcentaje: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class TemperaturaAmbienteModel(BaseModel):
    sensor: str
    id_sensor: Optional[int] = None
    valor: Optional[float] = None
    temperatura: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class TemperaturaSueloModel(BaseModel):
    sensor: str
    id_sensor: Optional[int] = None
    valor: Optional[float] = None
    temperatura: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class TelemetriaTanqueModel(BaseModel):
    sensor: str = "HC-SR04"
    id_sensor: Optional[int] = None
    distancia_cm: float
    estado_bomba: str
    fecha: Optional[datetime] = None


class RiegoDatosModel(BaseModel):
    humedad_suelo: HumedadSueloModel
    humedad_ambiente: HumedadAmbienteModel
    temperatura_ambiente: TemperaturaAmbienteModel
    temperatura_suelo: TemperaturaSueloModel


class PrediccionRiegoModel(BaseModel):
    humedad_suelo: float
    humedad_ambiente: float
    temperatura_ambiente: float
    temperatura_suelo: float


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


class BombaControlResponseModel(BaseModel):
    status: str
    accion: str
    topic: str


class DispositivoResponseModel(BaseModel):
    id_dispositivo: int
    id_usuario: Optional[int] = None
    id_tipo: int
    nombre: str
    mac_address: Optional[str] = None
    client_id_mqtt: Optional[str] = None
    topic_pub: Optional[str] = None
    topic_sub: Optional[str] = None
    ubicacion: Optional[str] = None
    estado: str
    funcionamiento_activo: bool
    fuente_agua: str
    altura_tanque_cm: Optional[float] = None
    distancia_seguridad_cm: Optional[float] = None
    bomba_encendida: bool
    valvula_abierta: bool
    ultimo_ping: Optional[datetime] = None
    firmware_version: Optional[str] = None
    fecha_registro: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


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

    model_config = {
        "from_attributes": True
    }


class SensorResponseModel(BaseModel):
    id_sensor: int
    id_dispositivo: int
    nombre: str
    id_tipo_metrica: int
    pin_gpio: Optional[int] = None
    estado: str
    fecha_registro: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class DispositivoConSensoresResponseModel(DispositivoResponseModel):
    sensores: List[SensorResponseModel] = []


class SensorConfigResponseModel(BaseModel):
    id_sensor: int
    nombre: str

    model_config = {
        "from_attributes": True
    }


class DispositivoConfigResponseModel(BaseModel):
    id_dispositivo: int
    id_usuario: Optional[int] = None
    id_tipo: int
    nombre: str
    client_id_mqtt: Optional[str] = None
    topic_pub: Optional[str] = None
    topic_sub: Optional[str] = None
    sensores: List[SensorConfigResponseModel] = []

    model_config = {
        "from_attributes": True
    }
