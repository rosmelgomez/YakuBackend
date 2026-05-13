from sqlalchemy import Column, DateTime, Double, Integer, String
from sqlalchemy.sql import func

from .conexion import Base


class humedad_suelo(Base):
    __tablename__ = "humedad_suelo"

    id = Column(Integer, primary_key=True, index=True)
    sensor = Column(String)
    valor = Column(Double)
    fecha = Column(DateTime(timezone=True), default=func.now())
    porcentaje = Column(Double)


class humedad_ambiente(Base):
    __tablename__ = "humedad_ambiente"

    id = Column(Integer, primary_key=True, index=True)
    sensor = Column(String)
    valor = Column(Double)
    fecha = Column(DateTime(timezone=True), default=func.now())
    porcentaje = Column(Double)


class temperatura_ambiente(Base):
    __tablename__ = "temperatura_ambiente"

    id = Column(Integer, primary_key=True, index=True)
    sensor = Column(String)
    valor = Column(Double)
    fecha = Column(DateTime(timezone=True), default=func.now())
    temperatura = Column(Double)


class temperatura_suelo(Base):
    __tablename__ = "temperatura_suelo"

    id = Column(Integer, primary_key=True, index=True)
    sensor = Column(String)
    valor = Column(Double)
    fecha = Column(DateTime(timezone=True), default=func.now())
    temperatura = Column(Double)


class control_agua(Base):
    __tablename__ = "control_agua"

    id = Column(Integer, primary_key=True, index=True)
    sensor = Column(String, default="HC-SR04")
    distancia_cm = Column(Double)
    altura_referencia_cm = Column(Double)
    nivel_agua_cm = Column(Double)
    porcentaje_nivel = Column(Double)
    estado_bomba = Column(String)
    fecha = Column(DateTime(timezone=True), default=func.now())


