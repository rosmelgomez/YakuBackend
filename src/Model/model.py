from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.sql import func

from .conexion import Base


class humedad_suelo(Base):
    __tablename__ = "humedad_suelo"

    id = Column(Integer, primary_key=True, index=True)
    id_sensor = Column(Integer, ForeignKey("sensores.id"), nullable=False)
    valor = Column(Numeric(10, 2))
    porcentaje = Column(Numeric(10, 2))
    fecha = Column(DateTime, server_default=func.now())


class humedad_ambiente(Base):
    __tablename__ = "humedad_ambiente"

    id = Column(Integer, primary_key=True, index=True)
    id_sensor = Column(Integer, ForeignKey("sensores.id"), nullable=False)
    valor = Column(Numeric(10, 2))
    porcentaje = Column(Numeric(10, 2))
    fecha = Column(DateTime, server_default=func.now())


class temperatura_ambiente(Base):
    __tablename__ = "temperatura_ambiente"

    id = Column(Integer, primary_key=True, index=True)
    id_sensor = Column(Integer, ForeignKey("sensores.id"), nullable=False)
    valor = Column(Numeric(10, 2))
    temperatura = Column(Numeric(10, 2))
    fecha = Column(DateTime, server_default=func.now())


class temperatura_suelo(Base):
    __tablename__ = "temperatura_suelo"

    id = Column(Integer, primary_key=True, index=True)
    id_sensor = Column(Integer, ForeignKey("sensores.id"), nullable=False)
    valor = Column(Numeric(10, 2))
    temperatura = Column(Numeric(10, 2))
    fecha = Column(DateTime, server_default=func.now())


class control_agua(Base):
    __tablename__ = "control_agua"

    id = Column(Integer, primary_key=True, index=True)
    id_sensor = Column(Integer, ForeignKey("sensores.id"), nullable=False)
    distancia_cm = Column(Numeric(10, 2))
    altura_referencia_cm = Column(Numeric(10, 2))
    nivel_agua_cm = Column(Numeric(10, 2))
    porcentaje_nivel = Column(Numeric(10, 2))
    estado_bomba = Column(String(20))
    fecha = Column(DateTime, server_default=func.now())


class roles(Base):
    __tablename__ = "roles"

    id_rol = Column("id", Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    descripcion = Column(Text)


class usuarios(Base):
    __tablename__ = "usuarios"

    id_usuario = Column("id", Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    correo = Column(String(100), unique=True, nullable=False)
    contrasena = Column(String(255), nullable=False)
    id_rol = Column(Integer, ForeignKey("roles.id"))
    estado = Column(Boolean, server_default=text("true"))
    fecha_registro = Column(DateTime, server_default=func.now())


class modelos_ml(Base):
    __tablename__ = "modelos_ml"

    id_modelo = Column("id", Integer, primary_key=True, index=True)
    nombre_modelo = Column(String(100), nullable=False)
    algoritmo = Column(String(50), nullable=False)
    descripcion = Column(Text)
    version = Column(String(20))
    precision_modelo = Column(Numeric(5, 2))
    estado = Column(String(20), server_default=text("'activo'"))
    fecha_entrenamiento = Column(DateTime)
    fecha_registro = Column(DateTime, server_default=func.now())


class usuario_modelo(Base):
    __tablename__ = "usuario_modelo"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"))
    fecha_asignacion = Column(DateTime, server_default=func.now())
    activo = Column(Boolean, server_default=text("true"))


class dispositivos(Base):
    __tablename__ = "dispositivos"

    id_dispositivo = Column("id", Integer, primary_key=True, index=True)
    nombre = Column(String(100))
    mac_address = Column(String(100))
    ubicacion = Column(String(100))
    estado = Column(String(20), server_default=text("'activo'"))
    fecha_registro = Column(DateTime, server_default=func.now())


class sensores(Base):
    __tablename__ = "sensores"

    id_sensor = Column("id", Integer, primary_key=True, index=True)
    id_dispositivo = Column(Integer, ForeignKey("dispositivos.id"))
    nombre = Column(String(100))
    tipo_sensor = Column(String(50))
    unidad = Column(String(20))
    descripcion = Column(Text)
    estado = Column(String(20), server_default=text("'activo'"))
    fecha_registro = Column(DateTime, server_default=func.now())


class plantas(Base):
    __tablename__ = "plantas"

    id_planta = Column("id", Integer, primary_key=True, index=True)
    nombre = Column(String(100))
    tipo = Column(String(50))
    descripcion = Column(Text)
    humedad_minima = Column(Numeric(10, 2))
    humedad_maxima = Column(Numeric(10, 2))


class cultivos(Base):
    __tablename__ = "cultivos"

    id_cultivo = Column("id", Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_planta = Column(Integer, ForeignKey("plantas.id"))
    nombre = Column(String(100))
    etapa_crecimiento = Column(String(50))
    area_m2 = Column(Numeric(10, 2))
    fecha_siembra = Column(Date)
    estado = Column(String(20), server_default=text("'activo'"))


class predicciones_ml(Base):
    __tablename__ = "predicciones_ml"

    id_prediccion = Column(Integer, primary_key=True, index=True)
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"))
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"))
    humedad_suelo = Column(Numeric(10, 2))
    humedad_ambiente = Column(Numeric(10, 2))
    temperatura_ambiente = Column(Numeric(10, 2))
    temperatura_suelo = Column(Numeric(10, 2))
    recomendacion = Column(String(50))
    probabilidad = Column(Numeric(5, 2))
    fecha = Column(DateTime, server_default=func.now())


class riego(Base):
    __tablename__ = "riego"

    id_riego = Column(Integer, primary_key=True, index=True)
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"))
    id_modelo = Column(Integer, ForeignKey("modelos_ml.id"))
    tipo_riego = Column(String(20))
    duracion_segundos = Column(Integer)
    cantidad_agua_litros = Column(Numeric(10, 2))
    estado = Column(Boolean)
    fecha = Column(DateTime, server_default=func.now())


class alertas(Base):
    __tablename__ = "alertas"

    id_alerta = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"))
    id_cultivo = Column(Integer, ForeignKey("cultivos.id"))
    tipo_alerta = Column(String(50))
    mensaje = Column(Text)
    prioridad = Column(String(20))
    estado = Column(String(20), server_default=text("'activa'"))
    fecha = Column(DateTime, server_default=func.now())


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
    descripcion = Column(Text)
    fecha = Column(DateTime, server_default=func.now())


modelo_ml = modelos_ml
predicciones = predicciones_ml


