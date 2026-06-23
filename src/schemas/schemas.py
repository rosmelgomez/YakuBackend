from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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


class AlmacenCreate(BaseModel):
    nombre: str
    id_distrito: Optional[int] = None
    direccion: Optional[str] = None


class AlmacenResponseModel(BaseModel):
    id: int
    nombre: str
    id_distrito: Optional[int] = None
    distrito: Optional[DistritoResponseModel] = None
    direccion: Optional[str] = None
    fecha_registro: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class DispositivoResponseModel(BaseModel):
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
    id_almacen: Optional[int] = None
    almacen: Optional[AlmacenResponseModel] = None
    en_almacen: Optional[bool] = True
    estado: str
    fecha_registro: Optional[datetime] = None
    modelo: Optional[TipoComponenteResponseModel] = None

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


class RegionCreate(BaseModel):
    nombre: str


class ProvinciaCreate(BaseModel):
    id_region: int
    nombre: str


class DistritoCreate(BaseModel):
    id_provincia: int
    nombre: str


class UmbralPlantaSchema(BaseModel):
    id_tipo_metrica: int
    valor_minimo: Optional[float] = None
    valor_maximo: Optional[float] = None


class PlantaCreate(BaseModel):
    nombre: str
    tipo: Optional[str] = None
    descripcion: Optional[str] = None
    umbrales: Optional[List[UmbralPlantaSchema]] = None


class PlantaResponseModel(BaseModel):
    id: int
    nombre: str
    tipo: Optional[str] = None
    descripcion: Optional[str] = None
    umbrales: Optional[List[UmbralPlantaSchema]] = None

    model_config = {
        "from_attributes": True
    }


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
    id_tipo_metrica: int
    id_fuente_agua: Optional[int] = None


class CultivoCreate(BaseModel):
    id_planta: Optional[int] = None
    id_fuente_agua: Optional[int] = None
    id_distrito: Optional[int] = None
    lugar: Optional[str] = None
    nombre_planta: str
    etapa_crecimiento: Optional[str] = None
    area_m2: Optional[float] = None
    fecha_siembra: Optional[str] = None  # String format yyyy-mm-dd


class FuenteAguaCreate(BaseModel):
    nombre: str
    tipo: str  # 'tanque' o 'manguera'
    capacidad_litros: Optional[float] = None
    altura_tanque_cm: Optional[float] = None
    altura_seguridad_cm: Optional[float] = None


class TipoDispositivoResponseModel(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


class RolDetail(BaseModel):
    nombre: str

    model_config = {
        "from_attributes": True
    }


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
    rol: Optional[RolDetail] = None

    model_config = {
        "from_attributes": True
    }


class UserRegisterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=2, max_length=100)
    apellido: Optional[str] = Field(default=None, max_length=100)
    correo: EmailStr
    contrasena: str = Field(min_length=10, max_length=128)
    telefono: Optional[str] = Field(default=None, max_length=20)

    @field_validator("contrasena")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(char.islower() for char in value) or not any(char.isupper() for char in value):
            raise ValueError("La contrasena debe incluir mayusculas y minusculas")
        if not any(char.isdigit() for char in value):
            raise ValueError("La contrasena debe incluir al menos un numero")
        return value


class AdminUserCreateInput(UserRegisterInput):
    id_rol: int = Field(ge=1, le=2)


class UserRegisterResponse(BaseModel):
    success: bool
    message: str
    userId: int


class VerifyCredentialsInput(BaseModel):
    correo: str
    contrasena: str


class UserVerifyResponse(BaseModel):
    id: str
    name: str
    email: str
    rol: str


class UserBriefResponse(BaseModel):
    nombre: str

    model_config = {
        "from_attributes": True
    }


class CropBriefResponse(BaseModel):
    nombre_planta: str

    model_config = {
        "from_attributes": True
    }


class TipoMetricaResponseModel(BaseModel):
    id: int
    codigo: str
    nombre: str
    unidad: str
    descripcion: Optional[str] = None
    fecha_registro: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


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

    model_config = {
        "from_attributes": True
    }


class DispositivoAdminResponse(BaseModel):
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

    model_config = {
        "from_attributes": True
    }


class CultivoAdminResponse(BaseModel):
    id: int
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


class AdminMetricasResponse(BaseModel):
    total_usuarios: int
    total_dispositivos: int
    total_dispositivos_activos: int
    total_cultivos_activos: int
    alertas_pendientes: int


class LogSistemaResponse(BaseModel):
    id: int
    id_usuario: Optional[int] = None
    usuario_nombre: Optional[str] = None
    accion: str
    modulo: Optional[str] = None
    descripcion: Optional[str] = None
    ip_acceso: Optional[str] = None
    fecha: datetime

    model_config = {
        "from_attributes": True
    }


class MLPrediccionAdminResponse(BaseModel):
    id: int
    id_usuario: int
    id_cultivo: Optional[int] = None
    usuario_nombre: str
    cultivo_nombre: str
    modelo_nombre: str
    recomendacion: str
    probabilidad: float
    accion_ejecutada: bool
    fecha: datetime

    model_config = {
        "from_attributes": True
    }


class MLModelStatsResponse(BaseModel):
    id: int
    nombre_modelo: str
    algoritmo: str
    precision_modelo: Optional[float] = None
    precision_score: Optional[float] = None
    recall_score: Optional[float] = None
    f1_score: Optional[float] = None
    es_default: bool
    predicciones_totales: int

    model_config = {
        "from_attributes": True
    }


class UserFilterItem(BaseModel):
    id: int
    nombre: str
    apellido: Optional[str] = None
    correo: str

    model_config = {
        "from_attributes": True
    }


class CropFilterItem(BaseModel):
    id: int
    nombre_planta: str
    id_usuario: int

    model_config = {
        "from_attributes": True
    }


class AdminDashboardSummaryResponse(BaseModel):
    metricas: AdminMetricasResponse
    logs: List[LogSistemaResponse]
    predicciones: List[MLPrediccionAdminResponse]
    modelos: List[MLModelStatsResponse]
    consumo_semanal: List[dict]
    usuarios_filtro: List[UserFilterItem]
    cultivos_filtro: List[CropFilterItem]


