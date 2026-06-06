from datetime import datetime

from sqlalchemy.orm import Session

from .model import (
    telemetria_tanque,
    dispositivos,
    configuracion_tanque,
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


def _obtener_o_crear_sensor(
    db: Session,
    nombre: str,
    id_dispositivo: int | None = None,
    codigo_metrica: str | None = None,
) -> sensores:
    sensor = db.query(sensores).filter(sensores.nombre == nombre).first()
    if sensor is not None:
        return sensor

    if id_dispositivo is None:
        from .model import dispositivos
        primer_dispositivo = db.query(dispositivos).first()
        if primer_dispositivo:
            id_dispositivo = primer_dispositivo.id_dispositivo
        else:
            raise ValueError("No se puede crear el sensor porque no hay ningún dispositivo registrado.")

    id_tipo_metrica = 1
    if codigo_metrica is not None:
        from .model import tipos_metrica
        metrica_db = db.query(tipos_metrica).filter(tipos_metrica.codigo == codigo_metrica).first()
        if metrica_db:
            id_tipo_metrica = metrica_db.id

    sensor = sensores(
        id_dispositivo=id_dispositivo,
        nombre=nombre,
        id_tipo_metrica=id_tipo_metrica,
        estado="activo"
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return sensor


def crear_humedad_suelo(
    db: Session,
    sensor: str,
    valor: float | None,
    porcentaje: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
    id_dispositivo: int | None = None,
) -> humedad_suelo:
    sensor_registro = _obtener_o_crear_sensor(db, sensor, id_dispositivo=id_dispositivo, codigo_metrica="HUM_SUELO")
    registro = humedad_suelo(
        id_sensor=sensor_registro.id_sensor,
        valor=valor,
        porcentaje=porcentaje,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_humedad_ambiente(
    db: Session,
    sensor: str,
    valor: float | None,
    porcentaje: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
    id_dispositivo: int | None = None,
) -> humedad_ambiente:
    sensor_registro = _obtener_o_crear_sensor(db, sensor, id_dispositivo=id_dispositivo, codigo_metrica="HUM_AMB")
    registro = humedad_ambiente(
        id_sensor=sensor_registro.id_sensor,
        valor=valor,
        porcentaje=porcentaje,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_temperatura_ambiente(
    db: Session,
    sensor: str,
    valor: float | None,
    temperatura: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
    id_dispositivo: int | None = None,
) -> temperatura_ambiente:
    sensor_registro = _obtener_o_crear_sensor(db, sensor, id_dispositivo=id_dispositivo, codigo_metrica="TEMP_AMB")
    registro = temperatura_ambiente(
        id_sensor=sensor_registro.id_sensor,
        valor=valor,
        temperatura=temperatura,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_temperatura_suelo(
    db: Session,
    sensor: str,
    valor: float | None,
    temperatura: float | None,
    ema: float | None = None,
    desviacion: float | None = None,
    valido: bool | None = True,
    fecha: datetime | None = None,
    id_dispositivo: int | None = None,
) -> temperatura_suelo:
    sensor_registro = _obtener_o_crear_sensor(db, sensor, id_dispositivo=id_dispositivo, codigo_metrica="TEMP_SUELO")
    registro = temperatura_suelo(
        id_sensor=sensor_registro.id_sensor,
        valor=valor,
        temperatura=temperatura,
        ema=ema,
        desviacion=desviacion,
        valido=valido if valido is not None else True,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def crear_datos_riego(
    db: Session,
    data: RiegoDatosModel,
    id_dispositivo: int | None = None,
) -> None:
    crear_humedad_suelo(
        db,
        sensor=data.humedad_suelo.sensor,
        valor=data.humedad_suelo.valor,
        porcentaje=data.humedad_suelo.porcentaje,
        ema=data.humedad_suelo.ema,
        desviacion=data.humedad_suelo.desviacion,
        valido=data.humedad_suelo.valido,
        fecha=data.humedad_suelo.fecha,
        id_dispositivo=id_dispositivo,
    )
    crear_humedad_ambiente(
        db,
        sensor=data.humedad_ambiente.sensor,
        valor=data.humedad_ambiente.valor,
        porcentaje=data.humedad_ambiente.porcentaje,
        ema=data.humedad_ambiente.ema,
        desviacion=data.humedad_ambiente.desviacion,
        valido=data.humedad_ambiente.valido,
        fecha=data.humedad_ambiente.fecha,
        id_dispositivo=id_dispositivo,
    )
    crear_temperatura_ambiente(
        db,
        sensor=data.temperatura_ambiente.sensor,
        valor=data.temperatura_ambiente.valor,
        temperatura=data.temperatura_ambiente.temperatura,
        ema=data.temperatura_ambiente.ema,
        desviacion=data.temperatura_ambiente.desviacion,
        valido=data.temperatura_ambiente.valido,
        fecha=data.temperatura_ambiente.fecha,
        id_dispositivo=id_dispositivo,
    )
    crear_temperatura_suelo(
        db,
        sensor=data.temperatura_suelo.sensor,
        valor=data.temperatura_suelo.valor,
        temperatura=data.temperatura_suelo.temperatura,
        ema=data.temperatura_suelo.ema,
        desviacion=data.temperatura_suelo.desviacion,
        valido=data.temperatura_suelo.valido,
        fecha=data.temperatura_suelo.fecha,
        id_dispositivo=id_dispositivo,
    )


def listar_humedad_suelo(db: Session) -> list[humedad_suelo]:
    return db.query(humedad_suelo).order_by(humedad_suelo.id.desc()).all()


def listar_humedad_ambiente(db: Session) -> list[humedad_ambiente]:
    return db.query(humedad_ambiente).order_by(humedad_ambiente.id.desc()).all()


def listar_temperatura_ambiente(db: Session) -> list[temperatura_ambiente]:
    return db.query(temperatura_ambiente).order_by(temperatura_ambiente.id.desc()).all()


def listar_temperatura_suelo(db: Session) -> list[temperatura_suelo]:
    return db.query(temperatura_suelo).order_by(temperatura_suelo.id.desc()).all()


def crear_telemetria_tanque(
    db: Session,
    sensor: str,
    distancia_cm: float,
    estado_bomba: str,
    fecha: datetime | None = None,
    id_dispositivo: int | None = None,
) -> telemetria_tanque:
    sensor_registro = _obtener_o_crear_sensor(db, sensor, id_dispositivo=id_dispositivo, codigo_metrica="NIVEL_AGUA")
    
    # Buscar configuración del tanque del dispositivo y obtener su altura configurada
    config = db.query(configuracion_tanque).filter(configuracion_tanque.id_dispositivo == sensor_registro.id_dispositivo).first()
    altura_tanque = 30.0  # valor por defecto si no está configurado
    
    if config is not None:
        if config.altura_tanque_cm is not None:
            altura_tanque = float(config.altura_tanque_cm)
        
        # Actualizar estado actual de la bomba
        config.bomba_encendida = (estado_bomba == "ON")
        db.add(config)

    nivel_agua_cm = max(altura_tanque - distancia_cm, 0.0)
    porcentaje_nivel = max(0.0, min((nivel_agua_cm / altura_tanque) * 100.0, 100.0))

    registro = telemetria_tanque(
        id_sensor=sensor_registro.id_sensor,
        distancia_cm=distancia_cm,
        nivel_agua_cm=nivel_agua_cm,
        porcentaje_nivel=porcentaje_nivel,
        estado_bomba=estado_bomba,
        fecha=fecha or datetime.now(),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def listar_telemetria_tanque(db: Session) -> list[telemetria_tanque]:
    return db.query(telemetria_tanque).order_by(telemetria_tanque.id.desc()).all()


def obtener_modelo_por_nombre(db: Session, nombre_modelo: str) -> modelos_ml | None:
    return db.query(modelos_ml).filter(modelos_ml.nombre_modelo == nombre_modelo).first()


def listar_modelos_ml(db: Session) -> list[modelos_ml]:
    return db.query(modelos_ml).order_by(modelos_ml.id_modelo.desc()).all()


def obtener_modelo_activo(db: Session, id_usuario: int | None = None) -> modelos_ml | None:
    # 1. Intentar obtener el modelo activo asignado específicamente al usuario
    if id_usuario is not None:
        asignacion = db.query(usuario_modelo).filter(
            usuario_modelo.id_usuario == id_usuario,
            usuario_modelo.activo.is_(True)
        ).order_by(usuario_modelo.fecha_asignacion.desc()).first()
        
        if asignacion is not None:
            modelo = db.query(modelos_ml).filter(modelos_ml.id_modelo == asignacion.id_modelo).first()
            if modelo is not None:
                return modelo

    # 2. Si no hay asignación específica, intentar obtener cualquier modelo activo globalmente
    asignacion_global = db.query(usuario_modelo).filter(
        usuario_modelo.activo.is_(True)
    ).order_by(usuario_modelo.fecha_asignacion.desc()).first()
    
    if asignacion_global is not None:
        modelo = db.query(modelos_ml).filter(modelos_ml.id_modelo == asignacion_global.id_modelo).first()
        if modelo is not None:
            return modelo

    # 3. Fallback al modelo marcado como default en la base de datos
    return db.query(modelos_ml).filter(modelos_ml.es_default.is_(True)).first()



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


def registrar_seleccion_modelo_por_id(
    db: Session,
    id_usuario: int,
    id_modelo: int,
) -> modelos_ml:
    modelo = db.query(modelos_ml).filter(modelos_ml.id_modelo == id_modelo).first()
    if modelo is None:
        raise ValueError("Modelo ML no encontrado")

    db.query(usuario_modelo).filter(
        usuario_modelo.id_usuario == id_usuario,
        usuario_modelo.activo.is_(True),
    ).update({usuario_modelo.activo: False}, synchronize_session=False)

    asignacion = usuario_modelo(id_usuario=id_usuario, id_modelo=id_modelo, activo=True)
    historial = historial_modelos(
        id_usuario=id_usuario,
        id_modelo=id_modelo,
        accion="seleccionado",
        descripcion=f"Modelo {modelo.nombre_modelo} seleccionado por el usuario por ID {id_modelo}"
    )

    db.add_all([asignacion, historial])
    db.commit()
    db.refresh(modelo)
    return modelo



def registrar_prediccion_ml(
    db: Session,
    id_usuario: int,
    id_modelo: int,
    variables_entrada: dict,
    recomendacion: str,
    probabilidad: float | None,
    id_cultivo: int | None = None,
    accion_ejecutada: bool | None = None,
    fuente_accion: str | None = None,
) -> None:
    from .model import predicciones_ml

    prediccion = predicciones_ml(
        id_usuario=id_usuario,
        id_modelo=id_modelo,
        variables_entrada=variables_entrada,
        recomendacion=recomendacion,
        probabilidad=probabilidad,
        id_cultivo=id_cultivo,
        accion_ejecutada=accion_ejecutada,
        fuente_accion=fuente_accion,
    )
    db.add(prediccion)
    db.commit()