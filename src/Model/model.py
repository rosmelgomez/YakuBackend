from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text, ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .conexion import Base


class roles(Base):
    __tablename__ = "roles"

    id_rol = Column("id", Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    descripcion = Column(Text)


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


class tipos_dispositivo(Base):
    __tablename__ = "tipos_dispositivo"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text)


class dispositivos(Base):
    __tablename__ = "dispositivos"

    id_dispositivo = Column("id", Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    id_tipo = Column(Integer, ForeignKey("tipos_dispositivo.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    mac_address = Column(String(100), unique=True)
    client_id_mqtt = Column(String(100), unique=True)
    topic_pub = Column(String(150))
    topic_sub = Column(String(150))
    ubicacion = Column(String(150))
    estado = Column(String(20), server_default=text("'activo'"))
    funcionamiento_activo = Column(Boolean, server_default=text("true"))
    ultimo_ping = Column(DateTime)
    firmware_version = Column(String(20))
    fecha_registro = Column(DateTime, server_default=func.now())

    # Relación 1:1 con configuracion_tanque
    configuracion = relationship("configuracion_tanque", uselist=False, back_populates="dispositivo", cascade="all, delete-orphan")

    # Properties de compatibilidad hacia atrás
    @property
    def fuente_agua(self):
        return self.configuracion.fuente_agua if self.configuracion else "manguera"

    @fuente_agua.setter
    def fuente_agua(self, value):
        if not self.configuracion:
            self.configuracion = configuracion_tanque()
        self.configuracion.fuente_agua = value

    @property
    def altura_tanque_cm(self):
        return self.configuracion.altura_tanque_cm if self.configuracion else None

    @altura_tanque_cm.setter
    def altura_tanque_cm(self, value):
        if not self.configuracion:
            self.configuracion = configuracion_tanque()
        self.configuracion.altura_tanque_cm = value

    @property
    def distancia_seguridad_cm(self):
        return self.configuracion.distancia_seguridad_cm if self.configuracion else None

    @distancia_seguridad_cm.setter
    def distancia_seguridad_cm(self, value):
        if not self.configuracion:
            self.configuracion = configuracion_tanque()
        self.configuracion.distancia_seguridad_cm = value

    @property
    def bomba_encendida(self):
        return self.configuracion.bomba_encendida if self.configuracion else False

    @bomba_encendida.setter
    def bomba_encendida(self, value):
        if not self.configuracion:
            self.configuracion = configuracion_tanque()
        self.configuracion.bomba_encendida = value

    @property
    def valvula_abierta(self):
        return self.configuracion.valvula_abierta if self.configuracion else False

    @valvula_abierta.setter
    def valvula_abierta(self, value):
        if not self.configuracion:
            self.configuracion = configuracion_tanque()
        self.configuracion.valvula_abierta = value


class configuracion_tanque(Base):
    __tablename__ = "configuracion_tanque"

    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id", ondelete="CASCADE"), primary_key=True)
    fuente_agua = Column(String(30), server_default=text("'manguera'"))
    altura_tanque_cm = Column(Numeric(5, 2), nullable=False)
    distancia_seguridad_cm = Column(Numeric(5, 2), nullable=False)
    bomba_encendida = Column(Boolean, server_default=text("false"))
    valvula_abierta = Column(Boolean, server_default=text("false"))
    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now())

    dispositivo = relationship("dispositivos", back_populates="configuracion")


class tipos_metrica(Base):
    __tablename__ = "tipos_metrica"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), unique=True, nullable=False)
    nombre = Column(String(100), nullable=False)
    unidad = Column(String(20), nullable=False)
    descripcion = Column(Text)
    fecha_registro = Column(DateTime, server_default=func.now())


class sensores(Base):
    __tablename__ = "sensores"

    id_sensor = Column("id", Integer, primary_key=True, index=True)
    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    id_tipo_metrica = Column(Integer, ForeignKey("tipos_metrica.id"), nullable=False)
    pin_gpio = Column(Integer)
    estado = Column(String(20), server_default=text("'activo'"))
    fecha_registro = Column(DateTime, server_default=func.now())


class humedad_suelo(Base):
    __tablename__ = "humedad_suelo"

    id = Column(Integer, primary_key=True, index=True)
    id_sensor = Column(Integer, ForeignKey("sensores.id"), nullable=False)
    valor = Column(Numeric(10, 2))
    porcentaje = Column(Numeric(10, 2))
    ema = Column(Numeric(10, 2))
    desviacion = Column(Numeric(8, 3))
    valido = Column(Boolean, server_default=text("true"))
    fecha = Column(DateTime, server_default=func.now())


class humedad_ambiente(Base):
    __tablename__ = "humedad_ambiente"

    id = Column(Integer, primary_key=True, index=True)
    id_sensor = Column(Integer, ForeignKey("sensores.id"), nullable=False)
    valor = Column(Numeric(10, 2))
    porcentaje = Column(Numeric(10, 2))
    ema = Column(Numeric(10, 2))
    desviacion = Column(Numeric(8, 3))
    valido = Column(Boolean, server_default=text("true"))
    fecha = Column(DateTime, server_default=func.now())


class temperatura_ambiente(Base):
    __tablename__ = "temperatura_ambiente"

    id = Column(Integer, primary_key=True, index=True)
    id_sensor = Column(Integer, ForeignKey("sensores.id"), nullable=False)
    valor = Column(Numeric(10, 2))
    temperatura = Column(Numeric(10, 2))
    ema = Column(Numeric(10, 2))
    desviacion = Column(Numeric(8, 3))
    valido = Column(Boolean, server_default=text("true"))
    fecha = Column(DateTime, server_default=func.now())


class temperatura_suelo(Base):
    __tablename__ = "temperatura_suelo"

    id = Column(Integer, primary_key=True, index=True)
    id_sensor = Column(Integer, ForeignKey("sensores.id"), nullable=False)
    valor = Column(Numeric(10, 2))
    temperatura = Column(Numeric(10, 2))
    ema = Column(Numeric(10, 2))
    desviacion = Column(Numeric(8, 3))
    valido = Column(Boolean, server_default=text("true"))
    fecha = Column(DateTime, server_default=func.now())


class telemetria_tanque(Base):
    __tablename__ = "telemetria_tanque"

    id = Column(Integer, primary_key=True, index=True)
    id_sensor = Column(Integer, ForeignKey("sensores.id"), nullable=False)
    distancia_cm = Column(Numeric(10, 2), nullable=False)
    nivel_agua_cm = Column(Numeric(10, 2))
    porcentaje_nivel = Column(Numeric(10, 2))
    estado_bomba = Column(String(20))
    fecha = Column(DateTime, server_default=func.now())


class plantas(Base):
    __tablename__ = "plantas"

    id_planta = Column("id", Integer, primary_key=True, index=True)
    nombre = Column(String(100))
    tipo = Column(String(50))
    descripcion = Column(Text)


class umbrales_planta(Base):
    __tablename__ = "umbrales_planta"

    id = Column(Integer, primary_key=True, index=True)
    id_planta = Column(Integer, ForeignKey("plantas.id"), nullable=False)
    id_tipo_metrica = Column(Integer, ForeignKey("tipos_metrica.id"), nullable=False)
    valor_minimo = Column(Numeric(10, 2))
    valor_maximo = Column(Numeric(10, 2))


class cultivos(Base):
    __tablename__ = "cultivos"

    id_cultivo = Column("id", Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_planta = Column(Integer, ForeignKey("plantas.id"))
    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id"))
    nombre_planta = Column(String(100), nullable=False)
    etapa_crecimiento = Column(String(50))
    area_m2 = Column(Numeric(10, 2))
    fecha_siembra = Column(Date)
    estado = Column(String(20), server_default=text("'activo'"))
    fecha_registro = Column(DateTime, server_default=func.now())


class umbrales_config(Base):
    __tablename__ = "umbrales_config"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"), nullable=True)
    id_tipo_metrica = Column(Integer, ForeignKey("tipos_metrica.id"), nullable=False)
    valor_minimo = Column(Numeric(10, 2))
    valor_maximo = Column(Numeric(10, 2))
    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now())


class configuracion_control(Base):
    __tablename__ = "configuracion_control"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"), nullable=True)
    duracion_riego_max_seg = Column(Integer, server_default=text("1800"))
    confianza_ml_minima = Column(Numeric(4, 3), server_default=text("0.70"))
    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now())


class modelos_ml(Base):
    __tablename__ = "modelos_ml"

    id_modelo = Column("id", Integer, primary_key=True, index=True)
    nombre_modelo = Column(String(100), nullable=False)
    algoritmo = Column(String(50), nullable=False)
    descripcion = Column(Text)
    ruta_archivo = Column(String(255))
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


class usuario_modelo(Base):
    __tablename__ = "usuario_modelo"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"))
    fecha_asignacion = Column(DateTime, server_default=func.now())
    activo = Column(Boolean, server_default=text("true"))


class predicciones_ml(Base):
    __tablename__ = "predicciones_ml"

    id_prediccion = Column("id", Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"))
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"))
    variables_entrada = Column(JSONB, nullable=False)
    recomendacion = Column(String(50))
    probabilidad = Column(Numeric(5, 2))
    accion_ejecutada = Column(Boolean)
    fuente_accion = Column(String(30))
    fecha = Column(DateTime, server_default=func.now())


class riego(Base):
    __tablename__ = "riego"

    id_riego = Column("id", Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id"))
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"))
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"))
    id_prediccion = Column(Integer, ForeignKey("predicciones_ml.id"))
    tipo_riego = Column(String(20))
    duracion_segundos = Column(Integer)
    cantidad_agua_litros = Column(Numeric(10, 2))
    motivo_cierre = Column(String(50))
    estado = Column(Boolean)
    fecha = Column(DateTime, server_default=func.now())


class programacion_riego(Base):
    __tablename__ = "programacion_riego"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id"), nullable=False)
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"), nullable=True)
    nombre = Column(String(100))
    dias_semana = Column(ARRAY(Integer), nullable=False)
    hora_inicio = Column(String(20), nullable=False)
    duracion_seg = Column(Integer, nullable=False, server_default=text("300"))
    activo = Column(Boolean, server_default=text("true"))
    ultima_ejecucion = Column(DateTime)
    fecha_registro = Column(DateTime, server_default=func.now())


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

    id_alerta = Column("id", Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_tipo_alerta = Column(Integer, ForeignKey("tipos_alerta.id"), nullable=False)
    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id"))
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


class configuracion_notificaciones(Base):
    __tablename__ = "configuracion_notificaciones"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_tipo_alerta = Column(Integer, ForeignKey("tipos_alerta.id"), nullable=False)
    activo = Column(Boolean, server_default=text("true"))
    canal_email = Column(Boolean, server_default=text("true"))
    canal_dashboard = Column(Boolean, server_default=text("true"))


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


class historial_modelos(Base):
    __tablename__ = "historial_modelos"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"))
    accion = Column(String(50))
    descripcion = Column(Text)
    fecha = Column(DateTime, server_default=func.now())


class logs_sistema(Base):
    __tablename__ = "logs_sistema"

    id_log = Column("id", Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    accion = Column(String(100))
    modulo = Column(String(50))
    descripcion = Column(Text)
    ip_acceso = Column(String(45))
    fecha = Column(DateTime, server_default=func.now())


modelo_ml = modelos_ml
predicciones = predicciones_ml
