from sqlalchemy.orm import Session, joinedload

from src.main.model.models import credenciales_mqtt_dispositivo, dispositivos


def queryListarDispositivosConCredencial(db: Session):
    """Todos los dispositivos con su credencial (o None), para el panel."""
    return (
        db.query(dispositivos, credenciales_mqtt_dispositivo)
        .options(joinedload(dispositivos.tipo))
        .outerjoin(
            credenciales_mqtt_dispositivo,
            credenciales_mqtt_dispositivo.id_dispositivo == dispositivos.id_dispositivo,
        )
        .order_by(dispositivos.nombre.asc(), dispositivos.id_dispositivo.asc())
        .all()
    )


def queryDispositivo(db: Session, id_dispositivo: int):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == id_dispositivo)
        .first()
    )


def queryCredencialPorDispositivo(db: Session, id_dispositivo: int):
    return (
        db.query(credenciales_mqtt_dispositivo)
        .filter(credenciales_mqtt_dispositivo.id_dispositivo == id_dispositivo)
        .first()
    )


def queryCredencialPorUsername(db: Session, username: str):
    return (
        db.query(credenciales_mqtt_dispositivo)
        .filter(credenciales_mqtt_dispositivo.username == username)
        .first()
    )
