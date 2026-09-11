from sqlalchemy.orm import Session

from src.main.model.models import plantas, umbrales_planta


def queryListarPlantasDbPlantas(db: Session):
    return db.query(plantas).order_by(plantas.nombre.asc()).all()


def queryListarPlantasDbUmbrales(db: Session, p):
    return (
        db.query(umbrales_planta).filter(umbrales_planta.id_planta == p.id_planta).all()
    )


def queryRegistrarPlantaExistente(db: Session, payload):
    return db.query(plantas).filter(plantas.nombre == payload.nombre).first()


def queryActualizarUmbralesPlantaPlanta(db: Session, planta_id):
    return db.query(plantas).filter(plantas.id_planta == planta_id).first()


def queryActualizarUmbralesPlantaConsultaActuales(db: Session, planta_id):
    return db.query(umbrales_planta).filter(umbrales_planta.id_planta == planta_id)


def queryActualizarUmbralesPlantaUmbralesPlanta(consulta_actuales, ids_metricas):
    return consulta_actuales.filter(
        ~umbrales_planta.id_tipo_metrica.in_(ids_metricas)
    ).delete(synchronize_session=False)


def queryActualizarUmbralesPlantaDelete(consulta_actuales):
    return consulta_actuales.delete(synchronize_session=False)


def queryActualizarUmbralesPlantaExistente(db: Session, planta_id, umbral):
    return (
        db.query(umbrales_planta)
        .filter(
            umbrales_planta.id_planta == planta_id,
            umbrales_planta.id_tipo_metrica == umbral.id_tipo_metrica,
        )
        .first()
    )
