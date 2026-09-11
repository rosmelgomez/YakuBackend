from sqlalchemy.orm import Session

from src.main.model.models import (
    cultivos,
    distritos,
    fuentes_agua,
    provincias,
    regiones,
)


def queryListarRegionesResultado(db: Session):
    return db.query(regiones).order_by(regiones.nombre.asc()).all()


def queryListarProvinciasPorRegionResultado(db: Session, id_region):
    return (
        db.query(provincias)
        .filter(provincias.id_region == id_region)
        .order_by(provincias.nombre.asc())
        .all()
    )


def queryListarDistritosPorProvinciaResultado(db: Session, id_provincia):
    return (
        db.query(distritos)
        .filter(distritos.id_provincia == id_provincia)
        .order_by(distritos.nombre.asc())
        .all()
    )


def queryListarTodasProvinciasResultado(db: Session):
    return db.query(provincias).order_by(provincias.nombre.asc()).all()


def queryListarTodosDistritosResultado(db: Session):
    return db.query(distritos).order_by(distritos.nombre.asc()).all()


def queryListarFuentesAguaUsuarioQuery(db: Session):
    return db.query(fuentes_agua).filter(fuentes_agua.activo == True)


def queryListarFuentesAguaUsuarioQuery2(query, id_usuario):
    return query.filter(fuentes_agua.id_usuario == id_usuario)


def queryListarFuentesAguaUsuarioResultado(query):
    return query.order_by(fuentes_agua.nombre.asc()).all()


def queryListarCultivosUsuarioResultado(db: Session):
    return db.query(cultivos).order_by(cultivos.id_cultivo.desc()).all()


def queryListarCultivosUsuarioResultado2(db: Session, current_user):
    return (
        db.query(cultivos)
        .filter(cultivos.id_usuario == current_user.id_usuario)
        .order_by(cultivos.id_cultivo.desc())
        .all()
    )


def queryRegistrarRegionExistente(db: Session, payload):
    return db.query(regiones).filter(regiones.nombre == payload.nombre).first()


def queryRegistrarProvinciaRegionExistente(db: Session, payload):
    return db.query(regiones).filter(regiones.id == payload.id_region).first()


def queryRegistrarProvinciaExistente(db: Session, payload):
    return (
        db.query(provincias)
        .filter(
            provincias.id_region == payload.id_region,
            provincias.nombre == payload.nombre,
        )
        .first()
    )


def queryRegistrarDistritoProvinciaExistente(db: Session, payload):
    return db.query(provincias).filter(provincias.id == payload.id_provincia).first()


def queryRegistrarDistritoExistente(db: Session, payload):
    return (
        db.query(distritos)
        .filter(
            distritos.id_provincia == payload.id_provincia,
            distritos.nombre == payload.nombre,
        )
        .first()
    )
