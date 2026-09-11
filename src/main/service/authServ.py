import hashlib
import logging
import secrets
from datetime import datetime

from fastapi import HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from src.main.core.rateLimit import enforce_rate_limit
from src.main.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from src.main.core.yakuConfig import COOKIE_SECURE
from src.main.dtos.authDto import (
    AuthModel,
    UserRegisterInput,
    UserUpdateInput,
    VerifyCredentialsInput,
)
from src.main.model.models import auth_sessions, logs_sistema, usuarios
from src.main.repositories import authRep as data_repository
from src.main.repositories import sessionRep as session_repository

logger = logging.getLogger(__name__)


_DUMMY_PASSWORD_HASH = hash_password("YakuDummyPassword2026")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_refresh_token(user: usuarios) -> tuple[str, auth_sessions]:
    session_id = secrets.token_urlsafe(24)
    refresh_token = create_refresh_token(
        subject=str(user.id_usuario),
        extra_claims={
            "correo": user.correo,
            "nombre": user.nombre,
            "id_rol": user.id_rol,
            "sid": session_id,
        },
    )
    payload = decode_access_token(refresh_token)
    session = auth_sessions(
        session_id=session_id,
        id_usuario=user.id_usuario,
        token_hash=_token_hash(refresh_token),
        expires_at=datetime.fromtimestamp(int(payload["exp"])),
    )
    return refresh_token, session


def get_current_user(
    cookie_token: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = None,
    db: Session = None,
) -> usuarios:
    token = None
    # 1. Intentar obtener el token desde la cookie (vía APIKeyCookie dependency)
    if cookie_token:
        token = cookie_token
    # 2. Intentar obtener el token desde el encabezado Authorization (Bearer)
    elif credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials

    user_id = None
    if token:
        try:
            payload = decode_access_token(token)
            if payload.get("type") == "access":
                user_id = int(payload.get("sub", "0"))
        except (ValueError, TypeError):
            user_id = None

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado o token expirado/inválido.",
        )

    user = data_repository.queryGetCurrentUserUser(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo",
        )

    return user


def loginServ(
    request: Request, response: Response, data: AuthModel, db: Session = None
):
    enforce_rate_limit(request, scope="login", limit=5, window_seconds=300)
    user = data_repository.queryLoginUser(db, data)

    password_hash = user.contrasena if user else _DUMMY_PASSWORD_HASH
    if not verify_password(data.contrasena, password_hash) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas"
        )

    access_token = create_access_token(
        subject=str(user.id_usuario),
        extra_claims={
            "correo": user.correo,
            "nombre": user.nombre,
            "id_rol": user.id_rol,
        },
    )
    refresh_token, refresh_session = _new_refresh_token(user)
    session_repository.add(db, refresh_session)
    session_repository.commit(db)

    # Determinar si la conexión es HTTPS de forma dinámica para desarrollo local (HTTP)
    is_secure = COOKIE_SECURE

    # Establecemos la cookie access_token httponly de forma segura
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    # Establecemos la cookie refresh_token httponly de forma segura
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )

    return {
        "status": "ok",
        "message": "Inicio de sesión exitoso",
    }


def refreshServ(
    request: Request,
    response: Response,
    refresh_token: str | None = None,
    db: Session = None,
):
    enforce_rate_limit(request, scope="refresh", limit=30, window_seconds=60)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado. Token de actualización faltante.",
        )

    try:
        payload = decode_access_token(refresh_token)
        # Verificar que el token sea de tipo refresh
        if payload.get("type") != "refresh":
            raise ValueError(
                "El token proporcionado no es un token de actualización válido"
            )
        user_id = int(payload.get("sub", "0"))
        session_id = str(payload.get("sid", ""))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de actualización inválido o expirado",
        ) from exc

    user = data_repository.queryRefreshUser(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo",
        )

    stored_session = data_repository.queryRefreshStoredSession(
        db, session_id, user_id, _token_hash(refresh_token)
    )
    if not stored_session or stored_session.expires_at <= datetime.now():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesion expirada o revocada",
        )
    stored_session.revoked = True
    stored_session.revoked_at = datetime.now()

    new_access_token = create_access_token(
        subject=str(user.id_usuario),
        extra_claims={
            "correo": user.correo,
            "nombre": user.nombre,
            "id_rol": user.id_rol,
        },
    )

    new_refresh_token, new_refresh_session = _new_refresh_token(user)
    session_repository.add(db, new_refresh_session)
    session_repository.commit(db)

    is_secure = COOKIE_SECURE

    # Establecemos la nueva cookie del Access Token
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )

    return {"status": "ok", "message": "Token renovado exitosamente"}


def logoutServ(
    request: Request, response: Response, current_user=None, db: Session = None
):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = decode_access_token(refresh_token)
            session_id = str(payload.get("sid", ""))
            stored_session = data_repository.queryLogoutStoredSession(
                db, session_id, current_user
            )
            if stored_session:
                stored_session.revoked = True
                stored_session.revoked_at = datetime.now()
                session_repository.commit(db)
        except (ValueError, TypeError):
            pass
    is_secure = COOKIE_SECURE
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=is_secure,
        samesite="lax",
    )
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=is_secure,
        samesite="lax",
    )
    return {"status": "ok", "message": "Sesión cerrada correctamente"}


def register_userServ(request: Request, data: UserRegisterInput, db: Session = None):
    enforce_rate_limit(request, scope="register", limit=3, window_seconds=3600)
    # 1. Validar si el usuario ya existe
    usuario_existente = data_repository.queryRegisterUserUsuarioExistente(db, data)
    if usuario_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya está registrado",
        )

    # 2. Hashear contraseña
    hashed_pwd = hash_password(data.contrasena)

    # 3. Crear el usuario con rol de agricultor (ID: 2)
    nuevo_usuario = usuarios(
        nombre=data.nombre,
        apellido=data.apellido,
        correo=data.correo,
        contrasena=hashed_pwd,
        telefono=data.telefono,
        id_rol=2,
        verificado=True,
        estado=True,
    )
    session_repository.add(db, nuevo_usuario)
    session_repository.commit(db)
    session_repository.refresh(db, nuevo_usuario)

    return {
        "success": True,
        "message": "Usuario registrado con éxito",
        "userId": nuevo_usuario.id_usuario,
    }


def verify_credentialsServ(
    request: Request, data: VerifyCredentialsInput, db: Session = None
):
    enforce_rate_limit(request, scope="verify-credentials", limit=5, window_seconds=300)
    # 1. Buscar usuario
    usuario = data_repository.queryVerifyCredentialsUsuario(db, data)
    password_hash = usuario.contrasena if usuario else _DUMMY_PASSWORD_HASH
    es_valido = verify_password(data.contrasena, password_hash)
    if not usuario or not usuario.estado or not es_valido:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas"
        )

    # 3. Registrar log de inicio de sesión
    try:
        nuevo_log = logs_sistema(
            id_usuario=usuario.id_usuario,
            accion="login",
            modulo="auth",
            descripcion=f"Inicio de sesión exitoso: {usuario.nombre}",
        )
        session_repository.add(db, nuevo_log)
        session_repository.commit(db)
    except Exception as e:
        logger.info(f"Error al registrar log: {e}")

    # 4. Obtener rol
    rol_obj = data_repository.queryVerifyCredentialsRolObj(db, usuario)
    rol_nombre = rol_obj.nombre if rol_obj else "agricultor"

    return {
        "id": str(usuario.id_usuario),
        "name": usuario.nombre,
        "email": usuario.correo,
        "rol": rol_nombre,
    }


def obtener_perfilServ(current_user=None):
    """
    Retorna el perfil completo del usuario autenticado.
    """
    return current_user


def actualizar_perfilServ(data: UserUpdateInput, db: Session = None, current_user=None):
    if data.correo != current_user.correo:
        correo_existente = data_repository.queryActualizarPerfilCorreoExistente(
            db, data, current_user
        )
        if correo_existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo ya está registrado por otro usuario",
            )
        current_user.correo = str(data.correo).lower()

    current_user.nombre = data.nombre
    current_user.apellido = data.apellido
    current_user.telefono = data.telefono

    if data.contrasena and len(data.contrasena.strip()) > 0:
        current_user.contrasena = hash_password(data.contrasena)
        data_repository.queryActualizarPerfilAuthSessions(db, current_user)

    session_repository.commit(db)
    session_repository.refresh(db, current_user)

    return {
        "success": True,
        "message": "Perfil actualizado con éxito",
        "name": current_user.nombre,
        "email": current_user.correo,
    }
