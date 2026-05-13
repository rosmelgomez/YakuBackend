from datetime import datetime

from sqlalchemy.orm import Session

from .model import (
    control_agua,
    humedad_ambiente,
    humedad_suelo,
    temperatura_ambiente,
    temperatura_suelo,
)


def crear_humedad_suelo(
    db: Session,
    sensor: str,
    valor: float,
    porcentaje: float,
    fecha: datetime | None = None,
) -> humedad_suelo:
    registro = humedad_suelo(
        sensor=sensor,
        valor=valor,
        porcentaje=porcentaje,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_humedad_ambiente(
    db: Session,
    sensor: str,
    valor: float,
    porcentaje: float,
    fecha: datetime | None = None,
) -> humedad_ambiente:
    registro = humedad_ambiente(
        sensor=sensor,
        valor=valor,
        porcentaje=porcentaje,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_temperatura_ambiente(
    db: Session,
    sensor: str,
    valor: float,
    temperatura: float,
    fecha: datetime | None = None,
) -> temperatura_ambiente:
    registro = temperatura_ambiente(
        sensor=sensor,
        valor=valor,
        temperatura=temperatura,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_temperatura_suelo(
    db: Session,
    sensor: str,
    valor: float,
    temperatura: float,
    fecha: datetime | None = None,
) -> temperatura_suelo:
    registro = temperatura_suelo(
        sensor=sensor,
        valor=valor,
        temperatura=temperatura,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_datos_riego(
    db: Session,
    humedad_suelo_data: humedad_suelo,
    humedad_ambiente_data: humedad_ambiente,
    temperatura_ambiente_data: temperatura_ambiente,
    temperatura_suelo_data: temperatura_suelo,
) -> None:
    db.add_all(
        [
            humedad_suelo_data,
            humedad_ambiente_data,
            temperatura_ambiente_data,
            temperatura_suelo_data,
        ]
    )
    db.commit()


def listar_humedad_suelo(db: Session) -> list[humedad_suelo]:
    return db.query(humedad_suelo).order_by(humedad_suelo.id.desc()).all()


def listar_humedad_ambiente(db: Session) -> list[humedad_ambiente]:
    return db.query(humedad_ambiente).order_by(humedad_ambiente.id.desc()).all()


def listar_temperatura_ambiente(db: Session) -> list[temperatura_ambiente]:
    return db.query(temperatura_ambiente).order_by(temperatura_ambiente.id.desc()).all()


def listar_temperatura_suelo(db: Session) -> list[temperatura_suelo]:
    return db.query(temperatura_suelo).order_by(temperatura_suelo.id.desc()).all()


def crear_control_agua(
    db: Session,
    sensor: str,
    distancia_cm: float,
    altura_referencia_cm: float,
    estado_bomba: str,
    fecha: datetime | None = None,
) -> control_agua:
    if altura_referencia_cm <= 0:
        raise ValueError("altura_referencia_cm debe ser mayor a 0")

    nivel_agua_cm = max(altura_referencia_cm - distancia_cm, 0.0)
    porcentaje_nivel = max(0.0, min((nivel_agua_cm / altura_referencia_cm) * 100, 100.0))

    registro = control_agua(
        sensor=sensor,
        distancia_cm=distancia_cm,
        altura_referencia_cm=altura_referencia_cm,
        nivel_agua_cm=nivel_agua_cm,
        porcentaje_nivel=porcentaje_nivel,
        estado_bomba=estado_bomba,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def listar_control_agua(db: Session) -> list[control_agua]:
    return db.query(control_agua).order_by(control_agua.id.desc()).all()