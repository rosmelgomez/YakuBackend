from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.main.db.databaseConexion import Base


class roles(Base):
    __tablename__ = "roles"

    id_rol = Column("id", Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    descripcion = Column(Text)


class almacenes(Base):
    __tablename__ = "almacenes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)
    id_distrito = Column(Integer, ForeignKey("distritos.id", ondelete="SET NULL"))
    direccion = Column(Text)
    fecha_registro = Column(DateTime, server_default=func.now())

    distrito = relationship("distritos")


class usuarios(Base):
    __tablename__ = "usuarios"

    id_usuario = Column("id", Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100))
    correo = Column(String(100), unique=True, nullable=False)
    contrasena = Column(String(255), nullable=False)
    id_rol = Column(Integer, ForeignKey("roles.id"))
    telefono = Column(String(20))
    zona_horaria = Column(String(50), server_default=text("'America/Lima'"))
    verificado = Column(Boolean, server_default=text("false"))
    estado = Column(Boolean, server_default=text("true"))
    ultimo_acceso = Column(DateTime)
    fecha_registro = Column(DateTime, server_default=func.now())
    dni = Column(String(20), unique=True, index=True)
    fecha_nacimiento = Column(Date)
    direccion = Column(String(255))
    fecha_modificacion = Column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    rol = relationship("roles")
    tokens = relationship(
        "tokens_usuario", back_populates="usuario", cascade="all, delete-orphan"
    )

    @property
    def id(self):
        return self.id_usuario


class tokens_usuario(Base):
    __tablename__ = "tokens_usuario"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(
        Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo = Column(String(30), nullable=False)  # 'verificacion' | 'recuperacion'
    token = Column(String(100), nullable=False, index=True)
    creado_en = Column(DateTime, nullable=False, server_default=func.now())
    expira_en = Column(DateTime, nullable=False)
    usado = Column(Boolean, nullable=False, server_default=text("false"), default=False)
    fecha_uso = Column(DateTime)
    ip_origen = Column(String(45))

    usuario = relationship("usuarios", back_populates="tokens")


class auth_sessions(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), nullable=False, unique=True, index=True)
    id_usuario = Column(
        Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    revoked_at = Column(DateTime)


class tipos_dispositivo(Base):
    __tablename__ = "tipos_dispositivo"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text)
    metodo_medicion = Column(String(20))


class dispositivos(Base):
    __tablename__ = "dispositivos"

    id_dispositivo = Column("id", Integer, primary_key=True, index=True)
    id_tipo = Column(Integer, ForeignKey("tipos_dispositivo.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    mac_address = Column(String(100), unique=True)
    client_id_mqtt = Column(String(100), unique=True)
    topic_pub = Column(String(150))
    topic_sub = Column(String(150))
    id_almacen = Column(Integer, ForeignKey("almacenes.id"))
    en_almacen = Column(Boolean, server_default=text("true"), default=True)
    estado = Column(String(20), server_default=text("'disponible'"))
    ultimo_ping = Column(DateTime)
    firmware_version = Column(String(20))
    fecha_registro = Column(DateTime, server_default=func.now())

    tipo = relationship("tipos_dispositivo")
    almacen = relationship("almacenes")

    # Relación hacia asignaciones
    asignaciones = relationship(
        "asignaciones_iot", back_populates="dispositivo", cascade="all, delete-orphan"
    )

    # Properties de compatibilidad hacia atrás
    @property
    def id(self):
        return self.id_dispositivo

    @property
    def metodo_medicion(self):
        return self.tipo.metodo_medicion if self.tipo else None

    @property
    def asignaciones_iot(self):
        return self.asignaciones

    @property
    def id_usuario(self):
        for asig in self.asignaciones:
            if asig.id_usuario:
                return asig.id_usuario
        return None

    @property
    def funcionamiento_activo(self):
        return any(asig.activo for asig in self.asignaciones)

    @funcionamiento_activo.setter
    def funcionamiento_activo(self, value):
        for asig in self.asignaciones:
            asig.activo = value

    @property
    def configuracion(self):
        for asig in self.asignaciones:
            if asig.configuracion:
                return asig.configuracion
        return None

    @property
    def fuente_agua(self):
        for asig in self.asignaciones:
            if asig.fuente_agua:
                return asig.fuente_agua.tipo
        return ""

    @property
    def altura_tanque_cm(self):
        for asig in self.asignaciones:
            if asig.fuente_agua:
                return asig.fuente_agua.altura_tanque_cm
        return None

    @property
    def altura_seguridad_cm(self):
        for asig in self.asignaciones:
            if asig.fuente_agua:
                return asig.fuente_agua.altura_seguridad_cm
        return None

    @property
    def bomba_encendida(self):
        config = self.configuracion
        return config.bomba_encendida if config else False

    @bomba_encendida.setter
    def bomba_encendida(self, value):
        config = self.configuracion
        if config:
            config.bomba_encendida = value

    @property
    def valvula_abierta(self):
        config = self.configuracion
        return config.valvula_abierta if config else False

    @valvula_abierta.setter
    def valvula_abierta(self, value):
        config = self.configuracion
        if config:
            config.valvula_abierta = value


class versiones_firmware(Base):
    __tablename__ = "versiones_firmware"
    __table_args__ = (
        UniqueConstraint(
            "version", "chip", "tipo_dispositivo", name="uq_firmware_release"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(30), nullable=False)
    chip = Column(String(30), nullable=False)
    tipo_dispositivo = Column(String(30), nullable=False)
    descripcion = Column(Text)
    manifiesto = Column(JSONB, nullable=False)
    directorio = Column(String(255), nullable=False)
    ubicacion_archivo = Column(String(500))
    publicado = Column(Boolean, nullable=False, server_default=text("true"))
    descontinuado = Column(Boolean, nullable=False, server_default=text("false"))
    creado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha_registro = Column(DateTime, nullable=False, server_default=func.now())
    fecha_descontinuado = Column(DateTime)


class instalaciones_firmware(Base):
    __tablename__ = "instalaciones_firmware"

    id = Column(Integer, primary_key=True, index=True)
    id_firmware = Column(Integer, ForeignKey("versiones_firmware.id"), nullable=False)
    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id"), nullable=False)
    id_administrador = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    chip_detectado = Column(String(50))
    mac_detectada = Column(String(100))
    estado = Column(String(30), nullable=False, server_default=text("'iniciada'"))
    progreso = Column(Integer, nullable=False, server_default=text("0"))
    mensaje = Column(Text)
    fecha_inicio = Column(DateTime, nullable=False, server_default=func.now())
    fecha_fin = Column(DateTime)


class tipos_metrica(Base):
    __tablename__ = "tipos_metrica"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), unique=True, nullable=False)
    nombre = Column(String(100), nullable=False)
    unidad = Column(String(20), nullable=False)
    descripcion = Column(Text)
    fecha_registro = Column(DateTime, server_default=func.now())


class tipos_componente(Base):
    __tablename__ = "tipos_componente"

    id = Column(Integer, primary_key=True, index=True)
    nombre_modelo = Column(String(100), unique=True, nullable=False)
    categoria = Column(String(30), nullable=False)
    id_tipo_metrica = Column(Integer, ForeignKey("tipos_metrica.id"))
    descripcion = Column(Text)


class componentes(Base):
    __tablename__ = "componentes"

    id = Column(Integer, primary_key=True, index=True)
    id_tipo_componente = Column(
        Integer, ForeignKey("tipos_componente.id"), nullable=False
    )
    numero_serie = Column(String(100), unique=True)
    id_almacen = Column(Integer, ForeignKey("almacenes.id"))
    en_almacen = Column(Boolean, server_default=text("true"), default=True)
    estado = Column(String(20), server_default=text("'disponible'"))
    fecha_registro = Column(DateTime, server_default=func.now())

    # Relación inversa al catálogo
    modelo = relationship("tipos_componente")
    almacen = relationship("almacenes")


class fuentes_agua(Base):
    __tablename__ = "fuentes_agua"
    __table_args__ = (
        CheckConstraint("tipo IN ('tanque', 'conexion_directa')", name='ck_fuentes_agua_tipo'),
        CheckConstraint("(tipo = 'conexion_directa' AND capacidad_litros IS NULL AND altura_tanque_cm IS NULL AND altura_seguridad_cm IS NULL) OR (tipo = 'tanque' AND capacidad_litros IS NOT NULL AND capacidad_litros > 0 AND capacidad_litros <= 99999999.99 AND altura_tanque_cm IS NOT NULL AND altura_tanque_cm > 0 AND altura_tanque_cm <= 9999.99 AND (altura_seguridad_cm IS NULL OR (altura_seguridad_cm >= 0 AND altura_seguridad_cm < altura_tanque_cm)))", name='ck_fuentes_agua_config'),
    )

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(30), nullable=False)
    capacidad_litros = Column(Numeric(10, 2))
    altura_tanque_cm = Column(Numeric(6, 2))
    altura_seguridad_cm = Column(Numeric(6, 2))
    activo = Column(Boolean, server_default=text("true"))
    fecha_registro = Column(DateTime, server_default=func.now())

    @property
    def capacidad_m3(self):
        return (
            float(self.capacidad_litros) / 1000.0
            if self.capacidad_litros is not None
            else None
        )

    @capacidad_m3.setter
    def capacidad_m3(self, value):
        self.capacidad_litros = float(value) * 1000.0 if value is not None else None


class plantas(Base):
    __tablename__ = "plantas"

    id_planta = Column("id", Integer, primary_key=True, index=True)
    nombre = Column(String(100))
    tipo = Column(String(50))
    descripcion = Column(Text)


class umbrales_planta(Base):
    __tablename__ = "umbrales_planta"

    id = Column(Integer, primary_key=True, index=True)
    id_planta = Column(
        Integer, ForeignKey("plantas.id", ondelete="CASCADE"), nullable=False
    )
    id_tipo_metrica = Column(Integer, ForeignKey("tipos_metrica.id"), nullable=False)
    valor_minimo = Column(Numeric(10, 2))
    valor_maximo = Column(Numeric(10, 2))


class regiones(Base):
    __tablename__ = "regiones"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False, unique=True)


class provincias(Base):
    __tablename__ = "provincias"

    id = Column(Integer, primary_key=True, index=True)
    id_region = Column(
        Integer, ForeignKey("regiones.id", ondelete="CASCADE"), nullable=False
    )
    nombre = Column(String(100), nullable=False)

    region = relationship("regiones")


class distritos(Base):
    __tablename__ = "distritos"

    id = Column(Integer, primary_key=True, index=True)
    id_provincia = Column(
        Integer, ForeignKey("provincias.id", ondelete="CASCADE"), nullable=False
    )
    nombre = Column(String(100), nullable=False)

    provincia = relationship("provincias")


class cultivos(Base):
    __tablename__ = "cultivos"

    id_cultivo = Column("id", Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_planta = Column(Integer, ForeignKey("plantas.id"))
    id_fuente_agua = Column(Integer, ForeignKey("fuentes_agua.id"))
    id_distrito = Column(Integer, ForeignKey("distritos.id"))
    lugar = Column(String(255))
    nombre_planta = Column(String(100), nullable=False)
    etapa_crecimiento = Column(String(50))
    area_m2 = Column(Numeric(10, 2))
    fecha_siembra = Column(Date)
    estado = Column(String(20), server_default=text("'activo'"))
    fecha_registro = Column(DateTime, server_default=func.now())

    distrito = relationship("distritos")

    @property
    def id(self):
        return self.id_cultivo

    fuente_agua = relationship("fuentes_agua")


class asignaciones_iot(Base):
    __tablename__ = "asignaciones_iot"
    __table_args__ = (
        Index(
            "unique_active_component_metric_assignment",
            "id_componente",
            "id_tipo_metrica",
            unique=True,
            postgresql_where=text("activo = true"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id"), nullable=False)
    id_componente = Column(Integer, ForeignKey("componentes.id"))
    id_fuente_agua = Column(Integer, ForeignKey("fuentes_agua.id"))
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"))
    id_tipo_metrica = Column(Integer, ForeignKey("tipos_metrica.id"))
    pin_gpio = Column(Integer)
    activo = Column(Boolean, server_default=text("false"))
    offset_calibracion = Column(Numeric(6, 2), server_default=text("0"))
    fecha_registro = Column(DateTime, server_default=func.now())

    # Relaciones
    dispositivo = relationship("dispositivos", back_populates="asignaciones")
    componente = relationship("componentes")
    cultivo = relationship("cultivos")
    fuente_agua = relationship("fuentes_agua")
    usuario = relationship("usuarios")
    tipo_metrica = relationship("tipos_metrica")
    configuracion = relationship(
        "configuracion_tanque",
        uselist=False,
        back_populates="asignacion",
        cascade="all, delete-orphan",
    )


class configuracion_tanque(Base):
    __tablename__ = "configuracion_tanque"

    id_asignacion = Column(
        Integer, ForeignKey("asignaciones_iot.id", ondelete="CASCADE"), primary_key=True
    )
    valvula_abierta = Column(Boolean, server_default=text("false"))
    bomba_encendida = Column(Boolean, server_default=text("false"))
    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now())

    asignacion = relationship("asignaciones_iot", back_populates="configuracion")


# =========================================================
# LECTURAS DE TELEMETRÍA
# =========================================================


class humedad_suelo(Base):
    __tablename__ = "humedad_suelo"

    id = Column(Integer, primary_key=True, index=True)
    id_asignacion = Column(
        Integer, ForeignKey("asignaciones_iot.id", ondelete="CASCADE"), nullable=False
    )
    valor = Column(Numeric(10, 2))
    porcentaje = Column(Numeric(10, 2))
    ema = Column(Numeric(10, 2))
    desviacion = Column(Numeric(8, 3))
    valido = Column(Boolean, server_default=text("true"))
    fecha = Column(DateTime, server_default=func.now())


class humedad_ambiente(Base):
    __tablename__ = "humedad_ambiente"

    id = Column(Integer, primary_key=True, index=True)
    id_asignacion = Column(
        Integer, ForeignKey("asignaciones_iot.id", ondelete="CASCADE"), nullable=False
    )
    valor = Column(Numeric(10, 2))
    porcentaje = Column(Numeric(10, 2))
    ema = Column(Numeric(10, 2))
    desviacion = Column(Numeric(8, 3))
    valido = Column(Boolean, server_default=text("true"))
    fecha = Column(DateTime, server_default=func.now())


class temperatura_ambiente(Base):
    __tablename__ = "temperatura_ambiente"

    id = Column(Integer, primary_key=True, index=True)
    id_asignacion = Column(
        Integer, ForeignKey("asignaciones_iot.id", ondelete="CASCADE"), nullable=False
    )
    valor = Column(Numeric(10, 2))
    temperatura = Column(Numeric(10, 2))
    ema = Column(Numeric(10, 2))
    desviacion = Column(Numeric(8, 3))
    valido = Column(Boolean, server_default=text("true"))
    fecha = Column(DateTime, server_default=func.now())


class temperatura_suelo(Base):
    __tablename__ = "temperatura_suelo"

    id = Column(Integer, primary_key=True, index=True)
    id_asignacion = Column(
        Integer, ForeignKey("asignaciones_iot.id", ondelete="CASCADE"), nullable=False
    )
    valor = Column(Numeric(10, 2))
    temperatura = Column(Numeric(10, 2))
    ema = Column(Numeric(10, 2))
    desviacion = Column(Numeric(8, 3))
    valido = Column(Boolean, server_default=text("true"))
    fecha = Column(DateTime, server_default=func.now())


class telemetria_tanque(Base):
    __tablename__ = "telemetria_tanque"
    __table_args__ = (
        CheckConstraint("litros_riego >= 0", name="ck_telemetria_litros_riego"),
        CheckConstraint("litros_acumulados >= 0", name="ck_telemetria_litros_acumulados"),
        CheckConstraint("caudal_l_min >= 0", name="ck_telemetria_caudal"),
        CheckConstraint("pulsos_riego >= 0", name="ck_telemetria_pulsos"),
        CheckConstraint("pulsos_por_litro > 0", name="ck_telemetria_calibracion"),
    )

    id = Column(Integer, primary_key=True, index=True)
    id_asignacion = Column(
        Integer, ForeignKey("asignaciones_iot.id", ondelete="CASCADE"), nullable=False
    )
    metodo_medicion = Column(String(20), nullable=False, server_default=text("'proximidad'"))
    distancia_cm = Column(Numeric(10, 2))
    litros_riego = Column(Numeric(14, 4))
    litros_acumulados = Column(Numeric(16, 4))
    caudal_l_min = Column(Numeric(12, 4))
    pulsos_riego = Column(BigInteger)
    pulsos_por_litro = Column(Numeric(12, 4))
    nivel_agua_cm = Column(Numeric(10, 2))
    porcentaje_nivel = Column(Numeric(10, 2))
    estado_nivel = Column(String(20))
    valvula_abierta = Column(Boolean, server_default=text("false"))
    bomba_encendida = Column(Boolean, server_default=text("false"))
    fuente_control = Column(String(30))
    fecha = Column(DateTime, server_default=func.now())

    @property
    def estado_bomba(self):
        return "ON" if self.bomba_encendida else "OFF"

    @estado_bomba.setter
    def estado_bomba(self, value):
        self.bomba_encendida = value == "ON"


class lecturas_bateria(Base):
    __tablename__ = "lecturas_bateria"

    id = Column(Integer, primary_key=True, index=True)
    id_asignacion = Column(
        Integer, ForeignKey("asignaciones_iot.id", ondelete="CASCADE"), nullable=False
    )
    porcentaje = Column(Numeric(5, 2), nullable=False)
    voltaje = Column(Numeric(4, 2))
    fecha = Column(DateTime, server_default=func.now())


# =========================================================
# UMBRALES, ML Y CONTROL
# =========================================================


class configuracion_umbrales(Base):
    __tablename__ = "configuracion_umbrales"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    id_cultivo = Column(
        Integer, ForeignKey("cultivos.id", ondelete="CASCADE"), nullable=True
    )
    id_tipo_metrica = Column(Integer, ForeignKey("tipos_metrica.id"), nullable=False)
    valor_minimo = Column(Numeric(10, 2))
    valor_maximo = Column(Numeric(10, 2))
    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now())


class configuracion_control(Base):
    __tablename__ = "configuracion_control"
    __table_args__ = (
        CheckConstraint(
            "duracion_riego_max_seg BETWEEN 60 AND 1800",
            name="ck_config_control_duracion_rele",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    id_cultivo = Column(
        Integer, ForeignKey("cultivos.id", ondelete="CASCADE"), nullable=True
    )
    duracion_riego_max_seg = Column(Integer, server_default=text("600"))
    cooldown_minutos = Column(Integer, server_default=text("30"))
    confianza_ml_minima = Column(Numeric(4, 3), server_default=text("0.70"))
    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now())


class modelos_ml(Base):
    __tablename__ = "modelos_ml"

    id_modelo = Column("id", Integer, primary_key=True, index=True)
    id_planta = Column(
        Integer, ForeignKey("plantas.id", ondelete="SET NULL"), nullable=True
    )
    nombre_modelo = Column(String(100), nullable=False)
    algoritmo = Column(String(50), nullable=False)
    descripcion = Column(Text)
    ruta_archivo = Column(String(255))
    ruta = Column(String(255))
    precision_modelo = Column(Numeric(5, 2))
    precision_score = Column(Numeric(5, 4))
    recall_score = Column(Numeric(5, 4))
    f1_score = Column(Numeric(5, 4))
    version = Column(String(20))
    es_default = Column(Boolean, server_default=text("false"))
    estado = Column(String(20), server_default=text("'activo'"))
    creado_por = Column(Integer, ForeignKey("usuarios.id"))
    fecha_entrenamiento = Column(DateTime)
    fecha_registro = Column(DateTime, server_default=func.now())

    planta = relationship("plantas")


class cultivo_modelo(Base):
    __tablename__ = "cultivo_modelo"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"))
    id_cultivo = Column(
        Integer, ForeignKey("cultivos.id", ondelete="CASCADE"), nullable=True
    )
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"))
    fecha_asignacion = Column(DateTime, server_default=func.now())
    activo = Column(Boolean, server_default=text("true"))


class historial_modelos(Base):
    __tablename__ = "historial_modelos"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"))
    accion = Column(String(50))
    descripcion = Column(Text)
    fecha = Column(DateTime, server_default=func.now())


class predicciones_ml(Base):
    __tablename__ = "predicciones_ml"

    id_prediccion = Column("id", Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"), nullable=False)
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"))
    variables_entrada = Column(JSONB, nullable=False)
    recomendacion = Column(String(50))
    probabilidad = Column(Numeric(5, 2))
    accion_ejecutada = Column(Boolean)
    fuente_accion = Column(String(30))
    fecha = Column(DateTime, server_default=func.now())


class riego(Base):
    __tablename__ = "riego"

    id = Column(Integer, primary_key=True, index=True)
    id_asignacion = Column(
        Integer, ForeignKey("asignaciones_iot.id", ondelete="CASCADE"), nullable=False
    )
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"))
    id_prediccion = Column(Integer, ForeignKey("predicciones_ml.id"))
    tipo_riego = Column(String(20), nullable=False)
    duracion_segundos = Column(Integer)
    segundos_acumulados = Column(Integer, server_default=text("0"))
    cantidad_agua_litros = Column(Numeric(10, 2))
    motivo_cierre = Column(String(50))
    estado = Column(Boolean, server_default=text("false"))
    fecha_inicio = Column(DateTime)
    fecha_fin = Column(DateTime)
    fecha = Column(DateTime, server_default=func.now())

    ejecuciones = relationship(
        "ejecucion_riego", back_populates="riego_rel", cascade="all, delete-orphan"
    )


class ejecucion_riego(Base):
    __tablename__ = "ejecuciones_riego"

    id = Column(Integer, primary_key=True, index=True)
    id_riego = Column(
        Integer, ForeignKey("riego.id", ondelete="CASCADE"), nullable=False
    )
    fecha_inicio = Column(DateTime, nullable=False, server_default=func.now())
    fecha_fin = Column(DateTime)
    metodo_medicion = Column(String(20))
    distancia_inicial_cm = Column(Numeric(6, 2))
    distancia_final_cm = Column(Numeric(6, 2))
    duracion_segundos = Column(Integer, server_default=text("0"))
    cantidad_agua_litros = Column(Numeric(10, 2), server_default=text("0.0"))
    motivo_cierre = Column(String(50))

    riego_rel = relationship("riego", back_populates="ejecuciones")


# =========================================================
# REPORTE DE CONSUMO DE AGUA
# =========================================================


class reporte_consumo_agua(Base):
    __tablename__ = "reporte_consumo_agua"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"))
    periodo_inicio = Column(Date, nullable=False)
    periodo_fin = Column(Date, nullable=False)
    consumo_total_litros = Column(Numeric(12, 3))
    consumo_manual_litros = Column(Numeric(12, 3))
    reduccion_porcentaje = Column(Numeric(5, 2))
    riegos_automaticos = Column(Integer)
    riegos_manuales = Column(Integer)
    riegos_programados = Column(Integer)
    duracion_total_segundos = Column(Integer)
    generado_en = Column(DateTime, server_default=func.now())


# =========================================================
# RETROALIMENTACION DE AGRICULTORES
# =========================================================


class feedback_agricultores(Base):
    __tablename__ = "feedback_agricultores"
    __table_args__ = (
        CheckConstraint(
            "calificacion BETWEEN 1 AND 5", name="ck_feedback_calificacion"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(
        Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_cultivo = Column(
        Integer,
        ForeignKey("cultivos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    modulo = Column(String(50), nullable=False)
    tipo = Column(String(30), nullable=False)
    calificacion = Column(Integer, nullable=False)
    mensaje = Column(Text, nullable=False)
    estado = Column(String(20), nullable=False, server_default=text("'nuevo'"))
    fecha = Column(DateTime, server_default=func.now(), nullable=False)

    usuario = relationship("usuarios")
    cultivo = relationship("cultivos")
    respuestas = relationship(
        "feedback_respuestas", back_populates="feedback", cascade="all, delete-orphan"
    )


class feedback_preguntas(Base):
    __tablename__ = "feedback_preguntas"

    id = Column(Integer, primary_key=True, index=True)
    pregunta = Column(Text, nullable=False)
    tipo = Column(String(20), nullable=False, server_default=text("'rating'"))
    obligatoria = Column(Boolean, nullable=False, server_default=text("true"))
    opciones = Column(JSON, nullable=True)
    descripcion = Column(Text)
    orden = Column(Integer, nullable=False, server_default=text("0"))
    activo = Column(Boolean, nullable=False, server_default=text("true"))
    fecha_registro = Column(DateTime, server_default=func.now(), nullable=False)
    actualizado_en = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    respuestas = relationship("feedback_respuestas", back_populates="pregunta")


class feedback_respuestas(Base):
    __tablename__ = "feedback_respuestas"
    __table_args__ = (
        CheckConstraint(
            "calificacion IS NULL OR (calificacion BETWEEN 1 AND 5)",
            name="ck_feedback_respuesta_calificacion",
        ),
        UniqueConstraint(
            "id_feedback", "id_pregunta", name="uq_feedback_respuesta_pregunta"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    id_feedback = Column(
        Integer,
        ForeignKey("feedback_agricultores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_pregunta = Column(
        Integer,
        ForeignKey("feedback_preguntas.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    calificacion = Column(Integer, nullable=True)
    respuesta_texto = Column(Text, nullable=True)
    fecha = Column(DateTime, server_default=func.now(), nullable=False)

    feedback = relationship("feedback_agricultores", back_populates="respuestas")
    pregunta = relationship("feedback_preguntas", back_populates="respuestas")


# =========================================================
# ALERTAS Y NOTIFICACIONES
# =========================================================


class tipos_alerta(Base):
    __tablename__ = "tipos_alerta"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), unique=True, nullable=False)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text)
    severidad = Column(String(20), nullable=False)
    activo = Column(Boolean, server_default=text("true"))


class alertas(Base):
    __tablename__ = "alertas"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_asignacion = Column(
        Integer, ForeignKey("asignaciones_iot.id", ondelete="CASCADE")
    )
    id_tipo_alerta = Column(Integer, ForeignKey("tipos_alerta.id"), nullable=False)
    id_tipo_metrica = Column(Integer, ForeignKey("tipos_metrica.id"))
    mensaje = Column(Text, nullable=False)
    prioridad = Column(String(20))
    valor_detectado = Column(Numeric(10, 2))
    umbral = Column(Numeric(10, 2))
    estado = Column(String(20), server_default=text("'pendiente'"))
    resuelta_por = Column(Integer, ForeignKey("usuarios.id"))
    resuelta_en = Column(DateTime)
    comentario = Column(Text)
    fecha = Column(DateTime, server_default=func.now())
    ultima_notificacion_en = Column(DateTime)
    proxima_notificacion_en = Column(DateTime)
    cantidad_notificaciones = Column(Integer, nullable=False, server_default=text("0"))
    ultimo_valor_detectado = Column(Numeric(10, 2))
    notificacion_leida = Column(Boolean, nullable=False, server_default=text("false"))
    notificacion_eliminada = Column(Boolean, nullable=False, server_default=text("false"))


class configuracion_notificaciones(Base):
    __tablename__ = "configuracion_notificaciones"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_tipo_alerta = Column(Integer, ForeignKey("tipos_alerta.id"), nullable=False)
    activo = Column(Boolean, server_default=text("true"))
    # Legacy column retained for old clients; operational email is disabled.
    canal_email = Column(Boolean, server_default=text("false"))
    canal_push = Column(Boolean, nullable=False, server_default=text("false"))
    canal_dashboard = Column(Boolean, server_default=text("true"))
    recordatorio_minutos = Column(Integer)


class notificaciones(Base):
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True, index=True)
    id_alerta = Column(Integer, ForeignKey("alertas.id"), nullable=False)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    canal = Column(String(20), nullable=False)
    asunto = Column(String(200))
    mensaje = Column(Text)
    enviado = Column(Boolean, server_default=text("false"))
    enviado_en = Column(DateTime)
    error = Column(Text)
    tipo_evento = Column(
        String(20), nullable=False, server_default=text("'activacion'")
    )
    intento = Column(Integer, nullable=False, server_default=text("1"))
    intentado_en = Column(DateTime, nullable=False, server_default=func.now())


class logs_sistema(Base):
    __tablename__ = "logs_sistema"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    accion = Column(String(100), nullable=False)
    modulo = Column(String(50))
    descripcion = Column(Text)
    ip_acceso = Column(String(45))
    fecha = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        server_default=text("(now() at time zone 'utc')"),
    )


class suscripciones_push(Base):
    __tablename__ = "suscripciones_push"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    endpoint = Column(Text, nullable=False, unique=True)
    key_p256dh = Column(Text, nullable=False)
    key_auth = Column(Text, nullable=False)
    fecha_registro = Column(DateTime, server_default=func.now())
