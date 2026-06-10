from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class HumedadSueloModel(BaseModel):
    id_asignacion: int
    valor: Optional[float] = None
    porcentaje: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class HumedadAmbienteModel(BaseModel):
    id_asignacion: int
    valor: Optional[float] = None
    porcentaje: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class TemperaturaAmbienteModel(BaseModel):
    id_asignacion: int
    valor: Optional[float] = None
    temperatura: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class TemperaturaSueloModel(BaseModel):
    id_asignacion: int
    valor: Optional[float] = None
    temperatura: Optional[float] = None
    ema: Optional[float] = None
    desviacion: Optional[float] = None
    valido: Optional[bool] = True
    fecha: Optional[datetime] = None


class TelemetriaTanqueModel(BaseModel):
    id_asignacion: int
    distancia_cm: float
    estado_bomba: str
    motivo_cierre: Optional[str] = None
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
    altura_seguridad_cm: Optional[float] = None
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


class TipoComponenteResponseModel(BaseModel):
    id: int
    nombre_modelo: str
    categoria: str
    id_tipo_metrica: Optional[int] = None
    descripcion: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


class ComponenteResponseModel(BaseModel):
    id: int
    id_tipo_componente: int
    numero_serie: Optional[str] = None
    estado: str
    fecha_registro: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }



class FuenteAguaResponseModel(BaseModel):
    id: int
    id_usuario: int
    nombre: str
    tipo: str
    capacidad_m3: Optional[float] = None
    altura_tanque_cm: Optional[float] = None
    altura_seguridad_cm: Optional[float] = None
    fecha_registro: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class AsignacionIoTResponseModel(BaseModel):
    id: int
    id_usuario: int
    id_dispositivo: int
    id_componente: Optional[int] = None
    id_fuente_agua: Optional[int] = None
    id_cultivo: Optional[int] = None
    pin_gpio: Optional[int] = None
    activo: bool
    fecha_registro: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class PlantillaRiegoResponseModel(BaseModel):
    id: int
    nombre: str
    dias_semana: List[int]
    hora_inicio: str
    duracion_seg: int

    model_config = {
        "from_attributes": True
    }


class ReporteConsumoAguaResponseModel(BaseModel):
    id: int
    id_usuario: int
    id_cultivo: Optional[int] = None
    periodo_inicio: object
    periodo_fin: object
    consumo_total_litros: Optional[float] = None
    consumo_manual_litros: Optional[float] = None
    reduccion_porcentaje: Optional[float] = None
    riegos_automaticos: Optional[int] = None
    riegos_manuales: Optional[int] = None
    riegos_programados: Optional[int] = None
    duracion_total_segundos: Optional[int] = None
    generado_en: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class RegionResponseModel(BaseModel):
    id: int
    nombre: str

    model_config = {
        "from_attributes": True
    }


class ProvinciaResponseModel(BaseModel):
    id: int
    id_region: int
    nombre: str

    model_config = {
        "from_attributes": True
    }


class DistritoResponseModel(BaseModel):
    id: int
    id_provincia: int
    nombre: str

    model_config = {
        "from_attributes": True
    }


class CultivoResponseModel(BaseModel):
    id_cultivo: int
    id_usuario: int
    id_planta: Optional[int] = None
    id_fuente_agua: Optional[int] = None
    id_distrito: Optional[int] = None
    lugar: Optional[str] = None
    nombre_planta: str
    etapa_crecimiento: Optional[str] = None
    area_m2: Optional[float] = None
    fecha_siembra: Optional[object] = None
    estado: str
    fecha_registro: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }