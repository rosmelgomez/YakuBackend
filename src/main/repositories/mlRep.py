"""Consultas y persistencia de modelos de aprendizaje automático."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.main.model.models import (
    asignaciones_iot,
    cultivo_modelo,
    historial_modelos,
    humedad_ambiente,
    humedad_suelo,
    modelos_ml,
    predicciones_ml,
    temperatura_ambiente,
    temperatura_suelo,
)


def listar_predicciones_ml(
    db: Session,
    id_usuario: int,
    id_cultivo: int | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limit: int = 50,
) -> list[predicciones_ml]:
    query = db.query(predicciones_ml).filter(predicciones_ml.id_usuario == id_usuario)
    if id_cultivo is not None:
        query = query.filter(predicciones_ml.id_cultivo == id_cultivo)
    if desde is not None:
        query = query.filter(predicciones_ml.fecha >= desde)
    if hasta is not None:
        query = query.filter(predicciones_ml.fecha <= hasta)
    return query.order_by(predicciones_ml.fecha.desc()).limit(limit).all()


def obtener_modelo_por_nombre(db: Session, nombre_modelo: str) -> modelos_ml | None:
    return (
        db.query(modelos_ml).filter(modelos_ml.nombre_modelo == nombre_modelo).first()
    )


def obtener_modelo_por_id(db: Session, id_modelo: int) -> modelos_ml | None:
    return db.query(modelos_ml).filter(modelos_ml.id_modelo == id_modelo).first()


def listar_modelos_ml(db: Session) -> list[modelos_ml]:
    return db.query(modelos_ml).order_by(modelos_ml.id_modelo.desc()).all()


def obtener_modelo_activo(
    db: Session, id_usuario: int | None = None, id_cultivo: int | None = None
) -> modelos_ml | None:
    # 1. Intentar obtener el modelo asignado al usuario y cultivo específico (activo o inactivo)
    if id_usuario is not None and id_cultivo is not None:
        asignacion = (
            db.query(cultivo_modelo)
            .filter(
                cultivo_modelo.id_usuario == id_usuario,
                cultivo_modelo.id_cultivo == id_cultivo,
            )
            .order_by(cultivo_modelo.fecha_asignacion.desc())
            .first()
        )

        if asignacion is not None:
            modelo = (
                db.query(modelos_ml)
                .filter(modelos_ml.id_modelo == asignacion.id_modelo)
                .first()
            )
            if modelo is not None:
                return modelo

    # 2. Si no se especificó cultivo, intentar obtener cualquier modelo activo globalmente del usuario
    if id_usuario is not None and id_cultivo is None:
        asignacion = (
            db.query(cultivo_modelo)
            .filter(
                cultivo_modelo.id_usuario == id_usuario, cultivo_modelo.activo.is_(True)
            )
            .order_by(cultivo_modelo.fecha_asignacion.desc())
            .first()
        )

        if asignacion is not None:
            modelo = (
                db.query(modelos_ml)
                .filter(modelos_ml.id_modelo == asignacion.id_modelo)
                .first()
            )
            if modelo is not None:
                return modelo

    # 3. Intentar obtener cualquier modelo activo globalmente en la tabla
    if id_cultivo is None:
        asignacion_global = (
            db.query(cultivo_modelo)
            .filter(cultivo_modelo.activo.is_(True))
            .order_by(cultivo_modelo.fecha_asignacion.desc())
            .first()
        )

        if asignacion_global is not None:
            modelo = (
                db.query(modelos_ml)
                .filter(modelos_ml.id_modelo == asignacion_global.id_modelo)
                .first()
            )
            if modelo is not None:
                return modelo

    # 3.5. Fallback al primer modelo activo compatible con la planta del cultivo
    if id_cultivo is not None:
        from src.main.model.models import cultivos

        cultivo = db.query(cultivos).filter(cultivos.id_cultivo == id_cultivo).first()
        if cultivo and cultivo.id_planta is not None:
            comp_model = (
                db.query(modelos_ml)
                .filter(
                    modelos_ml.id_planta == cultivo.id_planta,
                    modelos_ml.estado == "activo",
                )
                .order_by(modelos_ml.id_modelo.asc())
                .first()
            )
            if comp_model:
                return comp_model

    # 4. Fallback al modelo marcado como default
    return db.query(modelos_ml).filter(modelos_ml.es_default.is_(True)).first()


def registrar_seleccion_modelo(
    db: Session,
    id_usuario: int,
    nombre_modelo: str,
    algoritmo: str | None = None,
    descripcion: str | None = None,
    version: str | None = None,
    id_cultivo: int | None = None,
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

    query = db.query(cultivo_modelo).filter(
        cultivo_modelo.id_usuario == id_usuario,
        cultivo_modelo.activo.is_(True),
    )
    if id_cultivo is not None:
        query = query.filter(cultivo_modelo.id_cultivo == id_cultivo)
    query.update({cultivo_modelo.activo: False}, synchronize_session=False)

    asignacion = cultivo_modelo(
        id_usuario=id_usuario,
        id_cultivo=id_cultivo,
        id_modelo=modelo.id_modelo,
        activo=True,
    )
    historial = historial_modelos(
        id_usuario=id_usuario,
        id_modelo=modelo.id_modelo,
        accion="seleccionado",
        descripcion=f"Modelo {nombre_modelo} seleccionado por el usuario para el cultivo {id_cultivo}",
    )

    db.add_all([asignacion, historial])
    db.commit()
    db.refresh(modelo)
    return modelo


def registrar_seleccion_modelo_por_id(
    db: Session,
    id_usuario: int,
    id_modelo: int,
    id_cultivo: int | None = None,
) -> modelos_ml:
    modelo = db.query(modelos_ml).filter(modelos_ml.id_modelo == id_modelo).first()
    if modelo is None:
        raise ValueError("Modelo ML no encontrado")

    query = db.query(cultivo_modelo).filter(
        cultivo_modelo.id_usuario == id_usuario,
        cultivo_modelo.activo.is_(True),
    )
    if id_cultivo is not None:
        query = query.filter(cultivo_modelo.id_cultivo == id_cultivo)
    query.update({cultivo_modelo.activo: False}, synchronize_session=False)

    asignacion = cultivo_modelo(
        id_usuario=id_usuario, id_cultivo=id_cultivo, id_modelo=id_modelo, activo=True
    )
    historial = historial_modelos(
        id_usuario=id_usuario,
        id_modelo=id_modelo,
        accion="seleccionado",
        descripcion=f"Modelo {modelo.nombre_modelo} seleccionado por el usuario por ID {id_modelo} para el cultivo {id_cultivo}",
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
) -> predicciones_ml:
    from src.main.model.models import predicciones_ml

    prediccion = predicciones_ml(
        id_usuario=id_usuario,
        id_modelo=id_modelo,
        variables_entrada=variables_entrada,
        recomendacion=recomendacion,
        probabilidad=probabilidad,
        id_cultivo=id_cultivo,
        accion_ejecutada=accion_ejecutada,
        fuente_accion=fuente_accion,
        fecha=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(prediccion)
    db.commit()
    db.refresh(prediccion)
    return prediccion


from sqlalchemy import func, text
from sqlalchemy.orm import Session

from src.main.model.models import cultivos, dispositivos, modelos_ml, plantas, usuarios


def queryListarModelosCultivoDb(db: Session, id_cultivo):
    return db.query(cultivos).filter(cultivos.id_cultivo == id_cultivo).first()


def queryObtenerPrediccionRiegoPrimerUsuario(db: Session):
    return db.query(usuarios).order_by(usuarios.id_usuario.asc()).first()


def queryObtenerPrediccionRiegoQueryAsig(db: Session, id_usuario):
    return db.query(asignaciones_iot).filter(
        asignaciones_iot.id_usuario == id_usuario, asignaciones_iot.activo == True
    )


def queryObtenerPrediccionRiegoQueryAsig2(query_asig, id_dispositivo):
    return query_asig.filter(asignaciones_iot.id_dispositivo == id_dispositivo)


def queryObtenerPrediccionRiegoAsigDb(query_asig):
    return query_asig.first()


def queryObtenerPrediccionRiegoCultivoDb(db: Session, id_cultivo):
    return db.query(cultivos).filter(cultivos.id_cultivo == id_cultivo).first()


def queryTareaReentrenamientoModelRecord(db: Session):
    return db.query(modelos_ml).filter(modelos_ml.algoritmo == "RandomForest").first()


def queryEjecutarEntrenamientoDbPlantaDb(db: Session, nombre_busqueda):
    return (
        db.query(plantas)
        .filter(
            func.lower(plantas.nombre).like(f"%{nombre_busqueda.lower()}%")
            | func.lower(plantas.tipo).like(f"%{nombre_busqueda.lower()}%")
        )
        .first()
    )


def queryEjecutarEntrenamientoDbResult(db: Session, params, sql):
    return db.execute(text(sql), params).fetchall()


def queryEjecutarEntrenamientoDbUltimoModelo(db: Session, id_planta, algorithm):
    return (
        db.query(modelos_ml)
        .filter(
            modelos_ml.algoritmo
            == ("RandomForest" if algorithm == "rf" else "XGBoost"),
            modelos_ml.id_planta == id_planta,
        )
        .order_by(modelos_ml.id_modelo.desc())
        .first()
    )


def queryEjecutarPrediccionEnVivoSensorAsigs(db: Session, id_cultivo):
    # Sin el filtro de `activo`, una asignacion vieja/duplicada (desactivada
    # o huerfana) igual entraba en la busqueda de "la lectura mas reciente"
    # junto a la asignacion real -- si esa asignacion inactiva tenia una
    # lectura con fecha mas nueva (por cualquier desfase historico), el ML
    # terminaba clasificando con un valor obsoleto (ej. 100% de humedad de
    # suelo guardado hace dias) en vez del dato real actual.
    return (
        db.query(asignaciones_iot)
        .join(dispositivos)
        .filter(
            asignaciones_iot.id_cultivo == id_cultivo,
            asignaciones_iot.activo == True,  # noqa: E712
            dispositivos.id_tipo == 1,
        )
        .all()
    )


def queryEjecutarPrediccionEnVivoHSuelo(db: Session, sensor_asig_ids):
    return (
        db.query(humedad_suelo)
        .filter(
            humedad_suelo.id_asignacion.in_(sensor_asig_ids),
            humedad_suelo.valido == True,
        )
        .order_by(humedad_suelo.fecha.desc())
        .first()
    )


def queryEjecutarPrediccionEnVivoHAmb(db: Session, sensor_asig_ids):
    return (
        db.query(humedad_ambiente)
        .filter(
            humedad_ambiente.id_asignacion.in_(sensor_asig_ids),
            humedad_ambiente.valido == True,
        )
        .order_by(humedad_ambiente.fecha.desc())
        .first()
    )


def queryEjecutarPrediccionEnVivoTAmb(db: Session, sensor_asig_ids):
    return (
        db.query(temperatura_ambiente)
        .filter(
            temperatura_ambiente.id_asignacion.in_(sensor_asig_ids),
            temperatura_ambiente.valido == True,
        )
        .order_by(temperatura_ambiente.fecha.desc())
        .first()
    )


def queryEjecutarPrediccionEnVivoTSuelo(db: Session, sensor_asig_ids):
    return (
        db.query(temperatura_suelo)
        .filter(
            temperatura_suelo.id_asignacion.in_(sensor_asig_ids),
            temperatura_suelo.valido == True,
        )
        .order_by(temperatura_suelo.fecha.desc())
        .first()
    )
