from datetime import datetime

from sqlalchemy.orm import Session

from src.main.model.models import auth_sessions, roles, usuarios


def queryGetCurrentUserUser(db: Session, user_id):
    return (
        db.query(usuarios)
        .filter(usuarios.id_usuario == user_id, usuarios.estado.is_(True))
        .first()
    )


def queryLoginUser(db: Session, data):
    return (
        db.query(usuarios)
        .filter(
            (usuarios.correo == data.usuario) | (usuarios.nombre == data.usuario),
            usuarios.estado.is_(True),
        )
        .first()
    )


def queryRefreshUser(db: Session, user_id):
    return (
        db.query(usuarios)
        .filter(usuarios.id_usuario == user_id, usuarios.estado.is_(True))
        .first()
    )


def queryRefreshStoredSession(db: Session, session_id, user_id, token_hash_value):
    return (
        db.query(auth_sessions)
        .filter(
            auth_sessions.session_id == session_id,
            auth_sessions.id_usuario == user_id,
            auth_sessions.token_hash == token_hash_value,
            auth_sessions.revoked.is_(False),
        )
        .first()
    )


def queryLogoutStoredSession(db: Session, session_id, current_user):
    return (
        db.query(auth_sessions)
        .filter(
            auth_sessions.session_id == session_id,
            auth_sessions.id_usuario == current_user.id_usuario,
        )
        .first()
    )


def queryRegisterUserUsuarioExistente(db: Session, data):
    return db.query(usuarios).filter(usuarios.correo == data.correo).first()


def queryVerifyCredentialsUsuario(db: Session, data):
    return db.query(usuarios).filter(usuarios.correo == data.correo).first()


def queryVerifyCredentialsRolObj(db: Session, usuario):
    return db.query(roles).filter(roles.id_rol == usuario.id_rol).first()


def queryActualizarPerfilCorreoExistente(db: Session, data, current_user):
    return (
        db.query(usuarios)
        .filter(
            usuarios.correo == data.correo,
            usuarios.id_usuario != current_user.id_usuario,
        )
        .first()
    )


def queryActualizarPerfilAuthSessions(db: Session, current_user):
    return (
        db.query(auth_sessions)
        .filter(
            auth_sessions.id_usuario == current_user.id_usuario,
            auth_sessions.revoked.is_(False),
        )
        .update({"revoked": True, "revoked_at": datetime.now()})
    )
