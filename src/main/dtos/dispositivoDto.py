"""Contratos de datos del módulo dispositivo."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from src.main.dtos.almacenDto import AlmacenResponseModel
from src.main.dtos.commonDto import CropBriefResponse, UserBriefResponse


class DispositivoResponseModel(BaseModel):
    metodo_medicion: Optional[str] = None
    id_dispositivo: int
    id_usuario: Optional[int] = None
    id_tipo: int
    nombre: str
    mac_address: Optional[str] = None
    client_id_mqtt: Optional[str] = None
    topic_pub: Optional[str] = None
    topic_sub: Optional[str] = None
    id_almacen: Optional[int] = None
    almacen: Optional[AlmacenResponseModel] = None
    en_almacen: Optional[bool] = True
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

    model_config = {"from_attributes": True}


class SensorResponseModel(BaseModel):
    id_sensor: int
    id_dispositivo: int
    nombre: str
    id_tipo_metrica: int
    pin_gpio: Optional[int] = None
    estado: str
    fecha_registro: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DispositivoConSensoresResponseModel(DispositivoResponseModel):
    sensores: List[SensorResponseModel] = []


class SensorConfigResponseModel(BaseModel):
    id_sensor: int
    nombre: str

    model_config = {"from_attributes": True}


class DispositivoConfigResponseModel(BaseModel):
    id_dispositivo: int
    id_usuario: Optional[int] = None
    id_tipo: int
    nombre: str
    client_id_mqtt: Optional[str] = None
    topic_pub: Optional[str] = None
    topic_sub: Optional[str] = None
    sensores: List[SensorConfigResponseModel] = []

    model_config = {"from_attributes": True}


class TipoComponenteResponseModel(BaseModel):
    id: int
    nombre_modelo: str
    categoria: str
    id_tipo_metrica: Optional[int] = None
    descripcion: Optional[str] = None

    model_config = {"from_attributes": True}


class ComponenteResponseModel(BaseModel):
    id: int
    id_tipo_componente: int
    numero_serie: Optional[str] = None
    id_almacen: Optional[int] = None
    almacen: Optional[AlmacenResponseModel] = None
    en_almacen: Optional[bool] = True
    estado: str
    fecha_registro: Optional[datetime] = None
    modelo: Optional[TipoComponenteResponseModel] = None

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


class DiagnosticoSensorResponse(BaseModel):
    id_asignacion: int
    estado: str  # "Ok" o "Falla"
    motivo: str
    ultima_lectura_fecha: Optional[datetime] = None
    porcentaje_lecturas_invalidas: Optional[float] = None
    nota_voltaje: str = (
        "El firmware actual no reporta voltaje de batería; el diagnóstico se basa "
        "en conectividad y validez de las últimas lecturas."
    )


class DispositivoCreate(BaseModel):
    id_tipo: int
    nombre: str
    mac_address: Optional[str] = None
    client_id_mqtt: Optional[str] = None
    topic_pub: Optional[str] = None
    topic_sub: Optional[str] = None
    id_almacen: Optional[int] = None
    en_almacen: Optional[bool] = True
    estado: Optional[str] = "disponible"
    firmware_version: Optional[str] = None


class ComponenteCreate(BaseModel):
    id_tipo_componente: int
    numero_serie: Optional[str] = None
    id_almacen: Optional[int] = None
    en_almacen: Optional[bool] = True
    estado: Optional[str] = "disponible"


class AsignarComponentePayload(BaseModel):
    id_dispositivo: int
    id_componente: int
    pin_gpio: int
    id_tipo_metrica: Optional[int] = None
    id_fuente_agua: Optional[int] = None


class ActualizarAsignacionComponentePayload(BaseModel):
    pin_gpio: int
    id_tipo_metrica: Optional[int] = None
    id_fuente_agua: Optional[int] = None


class TipoDispositivoResponseModel(BaseModel):
    metodo_medicion: Optional[str] = None
    id: int
    nombre: str
    descripcion: Optional[str] = None

    model_config = {"from_attributes": True}


class TipoMetricaResponseModel(BaseModel):
    id: int
    codigo: str
    nombre: str
    unidad: str
    descripcion: Optional[str] = None
    fecha_registro: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AsignacionIoTAdminResponse(BaseModel):
    id: int
    id_usuario: int
    id_dispositivo: int
    id_componente: Optional[int] = None
    pin_gpio: Optional[int] = None
    id_fuente_agua: Optional[int] = None
    id_cultivo: Optional[int] = None
    id_tipo_metrica: Optional[int] = None
    activo: bool
    usuario: Optional[UserBriefResponse] = None
    cultivo: Optional[CropBriefResponse] = None
    componente: Optional[ComponenteResponseModel] = None
    tipo_metrica: Optional[TipoMetricaResponseModel] = None

    model_config = {"from_attributes": True}


class DispositivoAdminResponse(BaseModel):
    metodo_medicion: Optional[str] = None
    id: int
    id_dispositivo: int
    id_usuario: Optional[int] = None
    id_tipo: int
    nombre: str
    mac_address: Optional[str] = None
    client_id_mqtt: Optional[str] = None
    topic_pub: Optional[str] = None
    topic_sub: Optional[str] = None
    id_almacen: Optional[int] = None
    almacen: Optional[AlmacenResponseModel] = None
    en_almacen: Optional[bool] = True
    estado: str
    funcionamiento_activo: bool
    bomba_encendida: bool
    valvula_abierta: bool
    ultimo_ping: Optional[datetime] = None
    firmware_version: Optional[str] = None
    fecha_registro: Optional[datetime] = None
    tipo: Optional[TipoDispositivoResponseModel] = None
    asignaciones_iot: List[AsignacionIoTAdminResponse] = []

    model_config = {"from_attributes": True}
