from sqlalchemy.orm import Session

from src.main.model.models import (
    asignaciones_iot,
    cultivos,
    dispositivos,
    fuentes_agua,
    instalaciones_firmware,
    usuarios,
    versiones_firmware,
)


def queryBuildTankConfigSource(db: Session, source_id):
    return db.query(fuentes_agua).filter(fuentes_agua.id == source_id).first()


def queryListVersionsQuery(db: Session):
    return db.query(versiones_firmware)


def queryListVersionsQuery2(query):
    return query.filter(versiones_firmware.descontinuado == False)


def queryListVersionsVersions(query, firmware_sort_key_value):
    return query.order_by(*firmware_sort_key_value).all()


def queryCreateVersionPreviousVersions(db: Session, chip, device_type):
    return (
        db.query(versiones_firmware)
        .filter(
            versiones_firmware.chip == chip,
            versiones_firmware.tipo_dispositivo == device_type,
            versiones_firmware.descontinuado == False,
        )
        .all()
    )


def queryDownloadSegmentVersion(db: Session, version_id):
    return (
        db.query(versiones_firmware).filter(versiones_firmware.id == version_id).first()
    )


def queryDiscontinueVersionVersion(db: Session, version_id):
    return (
        db.query(versiones_firmware).filter(versiones_firmware.id == version_id).first()
    )


def queryGetProvisioningDevice(db: Session, device_id):
    return (
        db.query(dispositivos).filter(dispositivos.id_dispositivo == device_id).first()
    )


def queryGetProvisioningAssignments(db: Session, device_id):
    return (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id_dispositivo == device_id)
        .all()
    )


def queryGetProvisioningFarmer(db: Session, user_id):
    return db.query(usuarios).filter(usuarios.id_usuario == user_id).first()


def queryGetProvisioningCrop(db: Session, crop_id):
    return db.query(cultivos).filter(cultivos.id_cultivo == crop_id).first()


def queryCreateInstallationFirmware(db: Session, payload):
    return (
        db.query(versiones_firmware)
        .filter(versiones_firmware.id == payload.id_firmware)
        .first()
    )


def queryCreateInstallationDevice(db: Session, payload):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == payload.id_dispositivo)
        .first()
    )


def queryUpdateInstallationRecord(db: Session, installation_id):
    return (
        db.query(instalaciones_firmware)
        .filter(instalaciones_firmware.id == installation_id)
        .first()
    )


def queryUpdateInstallationFirmware(db: Session, record):
    return (
        db.query(versiones_firmware)
        .filter(versiones_firmware.id == record.id_firmware)
        .first()
    )


def queryUpdateInstallationDevice(db: Session, record):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == record.id_dispositivo)
        .first()
    )


def queryListInstallationsResultado(db: Session, safe_limit):
    return (
        db.query(instalaciones_firmware)
        .order_by(instalaciones_firmware.fecha_inicio.desc())
        .limit(safe_limit)
        .all()
    )


def querySincronizarFirmwaresDiscoVersions(db: Session):
    return (
        db.query(versiones_firmware)
        .filter(
            versiones_firmware.publicado == True,
            versiones_firmware.descontinuado == False,
        )
        .all()
    )
