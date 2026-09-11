from sqlalchemy.orm import Session

from src.main.model.models import (
    almacenes,
    asignaciones_iot,
    componentes,
    cultivo_modelo,
    cultivos,
    dispositivos,
    fuentes_agua,
    programacion_riego,
    usuarios,
)


def queryIsLastActiveAdminUsuarios(db: Session):
    return (
        db.query(usuarios)
        .filter(usuarios.id_rol == 1, usuarios.estado.is_(True))
        .count()
    )


def queryCrearUsuarioAdministrativoUsuarios(db: Session, normalized_email):
    return db.query(usuarios).filter(usuarios.correo == normalized_email).first()


def queryListarUsuariosSistemaResultado(db: Session):
    return db.query(usuarios).order_by(usuarios.id_usuario).all()


def queryCambiarEstadoUsuarioUser(db: Session, id_usuario):
    return db.query(usuarios).filter(usuarios.id_usuario == id_usuario).first()


def queryCambiarEstadoUsuarioPrimerAlmacen(db: Session):
    return db.query(almacenes).order_by(almacenes.id.asc()).first()


def queryCambiarEstadoUsuarioAsigs(db: Session, id_usuario):
    return (
        db.query(asignaciones_iot)
        .filter(
            asignaciones_iot.id_usuario == id_usuario, asignaciones_iot.activo == True
        )
        .all()
    )


def queryCambiarEstadoUsuarioDev(db: Session, asig):
    return (
        db.query(dispositivos)
        .filter(dispositivos.id_dispositivo == asig.id_dispositivo)
        .first()
    )


def queryCambiarEstadoUsuarioComp(db: Session, asig):
    return db.query(componentes).filter(componentes.id == asig.id_componente).first()


def queryCambiarEstadoUsuarioCultivos(db: Session, id_usuario):
    return (
        db.query(cultivos)
        .filter(cultivos.id_usuario == id_usuario, cultivos.estado == "activo")
        .update({cultivos.estado: "inactivo"}, synchronize_session=False)
    )


def queryCambiarEstadoUsuarioFuentesAgua(db: Session, id_usuario):
    return (
        db.query(fuentes_agua)
        .filter(fuentes_agua.id_usuario == id_usuario, fuentes_agua.activo == True)
        .update({fuentes_agua.activo: False}, synchronize_session=False)
    )


def queryCambiarEstadoUsuarioProgramacionRiego(db: Session, id_usuario):
    return (
        db.query(programacion_riego)
        .filter(
            programacion_riego.id_usuario == id_usuario,
            programacion_riego.activo == True,
        )
        .update({programacion_riego.activo: False}, synchronize_session=False)
    )


def queryCambiarEstadoUsuarioCultivoModelo(db: Session, id_usuario):
    return (
        db.query(cultivo_modelo)
        .filter(cultivo_modelo.id_usuario == id_usuario, cultivo_modelo.activo == True)
        .update({cultivo_modelo.activo: False}, synchronize_session=False)
    )


def queryCambiarRolUsuarioUser(db: Session, id_usuario):
    return db.query(usuarios).filter(usuarios.id_usuario == id_usuario).first()
