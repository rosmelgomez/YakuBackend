from datetime import datetime

from sqlalchemy.orm import Session

from .model import (
    control_agua,
    historial_modelos,
    humedad_ambiente,
    humedad_suelo,
    modelos_ml,
    sensores,
    temperatura_ambiente,
    temperatura_suelo,
    usuario_modelo,
)
from .schemas import RiegoDatosModel


def _obtener_o_crear_sensor(db: Session, nombre: str) -> sensores:
    sensor = db.query(sensores).filter(sensores.nombre == nombre).first()
    if sensor is not None:
        return sensor

    sensor = sensores(nombre=nombre, estado="activo")
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


def crear_humedad_suelo(
    db: Session,
    sensor: str,
    valor: float,
    porcentaje: float,
    fecha: datetime | None = None,
) -> humedad_suelo:
    sensor_registro = _obtener_o_crear_sensor(db, sensor)
    registro = humedad_suelo(
        id_sensor=sensor_registro.id_sensor,
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
    sensor_registro = _obtener_o_crear_sensor(db, sensor)
    registro = humedad_ambiente(
        id_sensor=sensor_registro.id_sensor,
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
    sensor_registro = _obtener_o_crear_sensor(db, sensor)
    registro = temperatura_ambiente(
        id_sensor=sensor_registro.id_sensor,
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
    sensor_registro = _obtener_o_crear_sensor(db, sensor)
    registro = temperatura_suelo(
        id_sensor=sensor_registro.id_sensor,
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
    data: RiegoDatosModel,
) -> None:
    crear_humedad_suelo(db, data.humedad_suelo.sensor, data.humedad_suelo.valor, data.humedad_suelo.porcentaje, data.humedad_suelo.fecha)
    crear_humedad_ambiente(db, data.humedad_ambiente.sensor, data.humedad_ambiente.valor, data.humedad_ambiente.porcentaje, data.humedad_ambiente.fecha)
    crear_temperatura_ambiente(db, data.temperatura_ambiente.sensor, data.temperatura_ambiente.valor, data.temperatura_ambiente.temperatura, data.temperatura_ambiente.fecha)
    crear_temperatura_suelo(db, data.temperatura_suelo.sensor, data.temperatura_suelo.valor, data.temperatura_suelo.temperatura, data.temperatura_suelo.fecha)


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

    sensor_registro = _obtener_o_crear_sensor(db, sensor)
    nivel_agua_cm = max(altura_referencia_cm - distancia_cm, 0.0)
    porcentaje_nivel = max(0.0, min((nivel_agua_cm / altura_referencia_cm) * 100, 100.0))

    registro = control_agua(
        id_sensor=sensor_registro.id_sensor,
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


def obtener_modelo_por_nombre(db: Session, nombre_modelo: str) -> modelos_ml | None:
    return db.query(modelos_ml).filter(modelos_ml.nombre_modelo == nombre_modelo).first()


def listar_modelos_ml(db: Session) -> list[modelos_ml]:
    return db.query(modelos_ml).order_by(modelos_ml.id_modelo.desc()).all()


def obtener_modelo_activo(db: Session, id_usuario: int | None = None) -> modelos_ml | None:
    query = db.query(usuario_modelo).filter(usuario_modelo.activo.is_(True))
    if id_usuario is not None:
        query = query.filter(usuario_modelo.id_usuario == id_usuario)

    asignacion = query.order_by(usuario_modelo.fecha_asignacion.desc()).first()
    if asignacion is None:
        return None

    return db.query(modelos_ml).filter(modelos_ml.id_modelo == asignacion.id_modelo).first()


def registrar_seleccion_modelo(
    db: Session,
    id_usuario: int,
    nombre_modelo: str,
    algoritmo: str | None = None,
    descripcion: str | None = None,
    version: str | None = None,
) -> modelos_ml:
    modelo = obtener_modelo_por_nombre(db, nombre_modelo)
    if modelo is None:
        modelo = modelos_ml(
            nombre_modelo=nombre_modelo,
            algoritmo=algoritmo or "desconocido",
            descripcion=descripcion,
            version=version,
            estado="activo",
        )
        db.add(modelo)
        db.flush()
    else:
        modelo.estado = "activo"
        if algoritmo:
            modelo.algoritmo = algoritmo
        if descripcion is not None:
            modelo.descripcion = descripcion
        if version is not None:
            modelo.version = version

    db.query(usuario_modelo).filter(
        usuario_modelo.id_usuario == id_usuario,
        usuario_modelo.activo.is_(True),
    ).update({usuario_modelo.activo: False}, synchronize_session=False)

    asignacion = usuario_modelo(id_usuario=id_usuario, id_modelo=modelo.id_modelo, activo=True)
    historial = historial_modelos(id_usuario=id_usuario, id_modelo=modelo.id_modelo, accion="seleccionado", descripcion=f"Modelo {nombre_modelo} seleccionado por el usuario")

    db.add_all([asignacion, historial])
    db.commit()
    db.refresh(modelo)
    return modelo


def registrar_prediccion_ml(
    db: Session,
    id_modelo: int,
    humedad_suelo: float,
    humedad_ambiente: float,
    temperatura_ambiente: float,
    temperatura_suelo: float,
    recomendacion: str,
    probabilidad: float | None,
) -> None:
    from .model import predicciones_ml

    prediccion = predicciones_ml(
        id_modelo=id_modelo,
        humedad_suelo=humedad_suelo,
        humedad_ambiente=humedad_ambiente,
        temperatura_ambiente=temperatura_ambiente,
        temperatura_suelo=temperatura_suelo,
        recomendacion=recomendacion,
        probabilidad=probabilidad,
    )
    db.add(prediccion)
    db.commit()