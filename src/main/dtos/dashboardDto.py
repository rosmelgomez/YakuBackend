"""Contratos de datos del módulo dashboard."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class BombaControlResponseModel(BaseModel):
    status: str
    accion: str
    topic: str


class PlantillaRiegoResponseModel(BaseModel):
    id: int
    nombre: str
    dias_semana: List[int]
    hora_inicio: str
    duracion_seg: int

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


class AdminMetricasResponse(BaseModel):
    total_usuarios: int
    total_dispositivos: int
    total_dispositivos_activos: int
    total_cultivos_activos: int


class LogSistemaResponse(BaseModel):
    id: int
    id_usuario: Optional[int] = None
    usuario_nombre: Optional[str] = None
    accion: str
    modulo: Optional[str] = None
    descripcion: Optional[str] = None
    ip_acceso: Optional[str] = None
    fecha: datetime

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


class UserFilterItem(BaseModel):
    id: int
    nombre: str
    apellido: Optional[str] = None
    correo: str

    model_config = {"from_attributes": True}


class CropFilterItem(BaseModel):
    id: int
    nombre_planta: str
    id_usuario: int

    model_config = {"from_attributes": True}


class AdminDashboardSummaryResponse(BaseModel):
    metricas: AdminMetricasResponse
    logs: List[LogSistemaResponse]
    predicciones: List[MLPrediccionAdminResponse]
    modelos: List[MLModelStatsResponse]
    consumo_semanal: List[dict]
    usuarios_filtro: List[UserFilterItem]
    cultivos_filtro: List[CropFilterItem]
    top_consumo: List[dict] = []
    registros_mensuales: List[dict] = []
    dispositivos_estado: List[dict] = []
    dispositivos_conectados: int = 0
    cultivos_por_planta: List[dict] = []
    zona_horaria: Optional[str] = None




class RelayDurationUpdateModel(BaseModel):
    idCultivo: int
    duracionMaxMinutos: int = Field(ge=1, le=30)


class CooldownUpdateModel(BaseModel):
    idCultivo: int
    cooldownMinutos: int = Field(ge=1, le=1440)


class TelemetriaBombaToggleModel(BaseModel):
    idTelemetria: int
    estado: bool


class RiegoStopModel(BaseModel):
    idCultivo: int
    motivo: Optional[str] = "cronometro_completado"


class UmbralUpdateItem(BaseModel):
    id: int
    min: float
    max: float


class UmbralesUpdateModel(BaseModel):
    idCultivo: int
    updates: List[UmbralUpdateItem]


class NotifConfigItemModel(BaseModel):
    id_tipo_alerta: int
    nombre: str
    canal_email: bool = False
    canal_push: bool = False
    recordatorio_minutos: int


class NotifConfigListModel(BaseModel):
    configs: List[NotifConfigItemModel]
    has_config: bool = False


class NotifConfigUpdateItem(BaseModel):
    id_tipo_alerta: int
    canal_email: bool = False
    canal_push: bool = False
    recordatorio_minutos: int = Field(ge=5, le=1440)


class NotifConfigUpdateModel(BaseModel):
    updates: List[NotifConfigUpdateItem]
