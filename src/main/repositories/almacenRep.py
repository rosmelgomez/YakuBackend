from sqlalchemy.orm import Session

from src.main.model.models import almacenes, componentes, dispositivos


def queryListarAlmacenesResultado(db: Session):
    return db.query(almacenes).order_by(almacenes.nombre.asc()).all()


def queryRegistrarAlmacenExistente(db: Session, payload):
    return db.query(almacenes).filter(almacenes.nombre == payload.nombre).first()


def queryEliminarAlmacenAlm(db: Session, almacen_id):
    return db.query(almacenes).filter(almacenes.id == almacen_id).first()


def queryEliminarAlmacenTieneDispositivos(db: Session, almacen_id):
    return db.query(dispositivos).filter(dispositivos.id_almacen == almacen_id).first()


def queryEliminarAlmacenTieneComponentes(db: Session, almacen_id):
    return db.query(componentes).filter(componentes.id_almacen == almacen_id).first()
