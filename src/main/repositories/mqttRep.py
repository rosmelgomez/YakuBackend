from sqlalchemy.orm import Session

from src.main.model.models import (
    asignaciones_iot,
    cultivo_modelo,
    dispositivos,
    fuentes_agua,
    humedad_ambiente,
    humedad_suelo,
    predicciones_ml,
    riego,
    temperatura_ambiente,
    temperatura_suelo,
    usuarios,
)


def queryProcesarMensajeAsig(db: Session, data):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id == data.humedad_suelo.id_asignacion)
        .first()
    )


def queryProcesarMensajePrimerUsuario(db: Session):
    return db.query(usuarios).order_by(usuarios.id_usuario.asc()).first()


def queryProcesarMensajeUsrMod(db: Session, id_usuario, id_cultivo):
    return (
        db.query(cultivo_modelo)
        .filter(
            cultivo_modelo.id_usuario == id_usuario,
            cultivo_modelo.id_cultivo == id_cultivo,
            cultivo_modelo.activo == True,
        )
        .first()
    )


def queryProcesarMensajeRiegoReciente(
    db: Session, id_cultivo, id_usuario, tiempo_cooldown
):
    return (
        db.query(riego)
        .join(asignaciones_iot, riego.id_asignacion == asignaciones_iot.id)
        .filter(
            asignaciones_iot.id_cultivo == id_cultivo,
            riego.id_usuario == id_usuario,
            riego.tipo_riego == "automatico_ml",
            riego.estado.is_(True),
            riego.fecha_fin.isnot(None),
            riego.fecha_fin >= tiempo_cooldown,
        )
        .order_by(riego.fecha_fin.desc())
        .first()
    )


def queryProcesarMensajePrediction(db: Session, id_usuario, id_cultivo):
    return (
        db.query(predicciones_ml)
        .filter(
            predicciones_ml.id_usuario == id_usuario,
            predicciones_ml.id_cultivo == id_cultivo,
        )
        .order_by(predicciones_ml.id_prediccion.desc())
        .first()
    )


def queryProcesarMensajeAsig2(db: Session, data):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id == data.id_asignacion)
        .first()
    )


def queryProcesarMensajeDevice(db: Session, client_id, payload):
    return (
        db.query(dispositivos)
        .filter(dispositivos.client_id_mqtt == (payload.get("client_id") or client_id))
        .first()
    )


def queryProcesarMensajeAsig3(db: Session, id_asignacion):
    return (
        db.query(asignaciones_iot).filter(asignaciones_iot.id == id_asignacion).first()
    )


def queryProcesarMensajeAsig4(db: Session, device):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_dispositivo == device.id_dispositivo,
            asignaciones_iot.activo == True,
        )
        .first()
    )


def queryProcesarMensajeAsig5(db: Session, device):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id_dispositivo == device.id_dispositivo)
        .order_by(asignaciones_iot.id.desc())
        .first()
    )


def queryProcesarMensajeFuente(db: Session, asig):
    return db.query(fuentes_agua).filter(fuentes_agua.id == asig.id_fuente_agua).first()


def queryProcesarMensajeOtroAsig(db: Session, asig):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_dispositivo == asig.id_dispositivo,
            asignaciones_iot.id_fuente_agua != None,
            asignaciones_iot.activo == True,
        )
        .first()
    )


def queryProcesarMensajeOtroAsig2(db: Session, asig):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_dispositivo == asig.id_dispositivo,
            asignaciones_iot.id_fuente_agua != None,
        )
        .first()
    )


def queryProcesarMensajeFuente2(db: Session, otro_asig):
    return (
        db.query(fuentes_agua)
        .filter(fuentes_agua.id == otro_asig.id_fuente_agua)
        .first()
    )


def queryProcesarMensajeUsrMod2(db: Session, asig):
    return (
        db.query(cultivo_modelo)
        .filter(
            cultivo_modelo.id_usuario == asig.id_usuario,
            cultivo_modelo.id_cultivo == asig.id_cultivo,
            cultivo_modelo.activo == True,
        )
        .first()
    )


def queryProcesarMensajeAsignaciones(db: Session, asig):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id_dispositivo == asig.id_dispositivo)
        .all()
    )


def queryUltimaLecturaValidaHumedadSuelo(db: Session, id_asignacion):
    return (
        db.query(humedad_suelo)
        .filter(humedad_suelo.id_asignacion == id_asignacion, humedad_suelo.valido == True)
        .order_by(humedad_suelo.fecha.desc())
        .first()
    )


def queryUltimaLecturaValidaHumedadAmbiente(db: Session, id_asignacion):
    return (
        db.query(humedad_ambiente)
        .filter(
            humedad_ambiente.id_asignacion == id_asignacion,
            humedad_ambiente.valido == True,
        )
        .order_by(humedad_ambiente.fecha.desc())
        .first()
    )


def queryUltimaLecturaValidaTemperaturaAmbiente(db: Session, id_asignacion):
    return (
        db.query(temperatura_ambiente)
        .filter(
            temperatura_ambiente.id_asignacion == id_asignacion,
            temperatura_ambiente.valido == True,
        )
        .order_by(temperatura_ambiente.fecha.desc())
        .first()
    )


def queryUltimaLecturaValidaTemperaturaSuelo(db: Session, id_asignacion):
    return (
        db.query(temperatura_suelo)
        .filter(
            temperatura_suelo.id_asignacion == id_asignacion,
            temperatura_suelo.valido == True,
        )
        .order_by(temperatura_suelo.fecha.desc())
        .first()
    )
