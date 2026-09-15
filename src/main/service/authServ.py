import hashlib
import logging
import secrets
from datetime import datetime, timedelta

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
from src.main.core.yakuConfig import COOKIE_SAMESITE, COOKIE_SECURE
from src.main.dtos.authDto import (
    AuthModel,
    PasswordResetConfirmInput,
    PasswordResetRequestInput,
    ResendCodeInput,
    UserRegisterInput,
    UserUpdateInput,
    VerifyCredentialsInput,
)
from src.main.model.models import (
    auth_sessions,
    logs_sistema,
    tokens_usuario,
    usuarios,
)
from src.main.repositories import authRep as data_repository
from src.main.repositories import sessionRep as session_repository
from src.main.service.notifications.emailServ import (
    enviar_codigo_recuperacion,
    enviar_codigo_verificacion,
)

logger = logging.getLogger(__name__)


_DUMMY_PASSWORD_HASH = hash_password("YakuDummyPassword2026")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _crear_token_usuario(
    db: Session,
    id_usuario: int,
    tipo: str,
    minutos_expiracion: int,
    ip_origen: str | None = None,
) -> str:
    """
    Genera un token numérico de 6 dígitos, invalida tokens previos no usados del mismo tipo
    e inserta el nuevo registro en tokens_usuario para mantener auditoría e histórico.
    """
    codigo = f"{secrets.randbelow(900000) + 100000:06d}"
    # Invalidar tokens anteriores del mismo tipo no consumidos
    db.query(tokens_usuario).filter(
        tokens_usuario.id_usuario == id_usuario,
        tokens_usuario.tipo == tipo,
        tokens_usuario.usado.is_(False),
    ).update({"usado": True, "fecha_uso": datetime.now()})

    nuevo_token = tokens_usuario(
        id_usuario=id_usuario,
        tipo=tipo,
        token=codigo,
        expira_en=datetime.now() + timedelta(minutes=minutos_expiracion),
        usado=False,
        ip_origen=ip_origen,
    )
    session_repository.add(db, nuevo_token)
    session_repository.commit(db)
    return codigo


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

    if getattr(user, "verificado", None) is False:
        client_ip = request.client.host if request.client else None
        nuevo_codigo = _crear_token_usuario(
            db, user.id_usuario, "verificacion", 30, client_ip
        )
        try:
            enviar_codigo_verificacion(
                destinatario=user.correo,
                nombre=user.nombre,
                codigo=nuevo_codigo,
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta no verificada. Hemos enviado un nuevo código de confirmación a tu correo.",
        )

    user.ultimo_acceso = datetime.now()

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
        samesite=COOKIE_SAMESITE,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    # Establecemos la cookie refresh_token httponly de forma segura
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_secure,
        samesite=COOKIE_SAMESITE,
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
        samesite=COOKIE_SAMESITE,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=is_secure,
        samesite=COOKIE_SAMESITE,
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
        samesite=COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=is_secure,
        samesite=COOKIE_SAMESITE,
    )
    return {"status": "ok", "message": "Sesión cerrada correctamente"}


def register_userServ(request: Request, data: UserRegisterInput, db: Session = None):
    enforce_rate_limit(request, scope="register", limit=3, window_seconds=3600)
    normalized_email = str(data.correo).strip().lower()
    # 1. Validar si el usuario ya existe
    usuario_existente = data_repository.queryRegisterUserUsuarioExistente(
        db, normalized_email
    )
    if usuario_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya está registrado",
        )

    # 1.1 Validar DNI si fue proporcionado
    if data.dni and data.dni.strip():
        dni_norm = data.dni.strip()
        dni_existente = (
            db.query(usuarios).filter(usuarios.dni == dni_norm).first()
        )
        if dni_existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El DNI ya está registrado por otro usuario",
            )

    # 2. Hashear contraseña
    hashed_pwd = hash_password(data.contrasena)

    # 3. Crear el usuario con rol de agricultor (ID: 2)
    nuevo_usuario = usuarios(
        nombre=data.nombre.strip(),
        apellido=data.apellido.strip() if data.apellido else None,
        correo=normalized_email,
        contrasena=hashed_pwd,
        telefono=data.telefono.strip() if data.telefono else None,
        zona_horaria=data.zona_horaria.strip() if data.zona_horaria else "America/Lima",
        dni=data.dni.strip() if data.dni else None,
        fecha_nacimiento=data.fecha_nacimiento,
        direccion=data.direccion.strip() if data.direccion else None,
        id_rol=2,
        verificado=False,
        estado=True,
    )
    session_repository.add(db, nuevo_usuario)
    session_repository.commit(db)
    session_repository.refresh(db, nuevo_usuario)

    # 3.1 Registrar token de verificación (validez 30 minutos) en tokens_usuario para trazabilidad
    client_ip = request.client.host if request.client else None
    codigo_verificacion = _crear_token_usuario(
        db, nuevo_usuario.id_usuario, "verificacion", 30, client_ip
    )

    # 4. Enviar correo con el código de confirmación
    try:
        enviar_codigo_verificacion(
            destinatario=nuevo_usuario.correo,
            nombre=nuevo_usuario.nombre,
            codigo=codigo_verificacion,
        )
    except Exception as e:
        logger.warning(f"Error al enviar código de verificación por correo: {e}")

    return {
        "success": True,
        "message": "Usuario registrado con éxito",
        "userId": nuevo_usuario.id_usuario,
        "verificationToken": codigo_verificacion,
    }


def reenviar_codigo_verificacionServ(
    request: Request, data: ResendCodeInput, db: Session = None
):
    enforce_rate_limit(request, scope="resend-code", limit=5, window_seconds=600)
    correo_norm = str(data.correo).strip().lower()
    user = db.query(usuarios).filter(usuarios.correo == correo_norm).first()
    if not user:
        return {
            "success": True,
            "message": "Si el correo está registrado, recibirás un nuevo código de confirmación.",
        }

    if user.verificado:
        return {
            "success": True,
            "message": "Tu cuenta ya se encuentra verificada. Puedes iniciar sesión.",
        }

    client_ip = request.client.host if request.client else None
    nuevo_codigo = _crear_token_usuario(
        db, user.id_usuario, "verificacion", 30, client_ip
    )

    try:
        enviar_codigo_verificacion(
            destinatario=user.correo,
            nombre=user.nombre,
            codigo=nuevo_codigo,
        )
    except Exception as e:
        logger.warning(f"Error al enviar reenvío de código: {e}")

    return {
        "success": True,
        "message": "Se ha enviado un nuevo código de confirmación a tu correo.",
    }


def verificar_tokenServ(token: str, correo: str | None = None, db: Session = None):
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de confirmación no proporcionado",
        )
    token_limpio = token.strip()
    query = (
        db.query(tokens_usuario)
        .join(usuarios, tokens_usuario.id_usuario == usuarios.id_usuario)
        .filter(
            tokens_usuario.token == token_limpio,
            tokens_usuario.tipo == "verificacion",
            tokens_usuario.usado.is_(False),
        )
    )
    if correo and correo.strip():
        query = query.filter(usuarios.correo == correo.strip().lower())
    token_reg = query.order_by(tokens_usuario.id.desc()).first()

    if not token_reg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Código de confirmación inválido o inexistente",
        )

    user = (
        db.query(usuarios)
        .filter(usuarios.id_usuario == token_reg.id_usuario)
        .first()
    )
    if not user or not user.estado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Código de confirmación inválido o inexistente",
        )
    if (
        token_reg.expira_en
        and token_reg.expira_en < datetime.now()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código de confirmación ha expirado. Por favor, solicita uno nuevo.",
        )

    user.verificado = True
    user.ultimo_acceso = datetime.now()
    token_reg.usado = True
    token_reg.fecha_uso = datetime.now()
    session_repository.commit(db)

    rol_obj = data_repository.queryVerifyCredentialsRolObj(db, user)
    rol_nombre = rol_obj.nombre if rol_obj else "agricultor"
    nombre_completo = (
        f"{user.nombre} {user.apellido}".strip()
        if user.apellido
        else user.nombre
    )

    return {
        "success": True,
        "message": "Correo verificado exitosamente",
        "user": {
            "id": str(user.id_usuario),
            "name": nombre_completo,
            "email": user.correo,
            "rol": rol_nombre,
        },
    }


def verify_credentialsServ(
    request: Request, data: VerifyCredentialsInput, db: Session = None
):
    enforce_rate_limit(request, scope="verify-credentials", limit=5, window_seconds=300)

    # Caso 1: Inicio de sesión / verificación mediante código o token
    if data.token and data.token.strip():
        token_limpio = data.token.strip()
        query = (
            db.query(tokens_usuario)
            .join(usuarios, tokens_usuario.id_usuario == usuarios.id_usuario)
            .filter(
                tokens_usuario.token == token_limpio,
                tokens_usuario.tipo == "verificacion",
                tokens_usuario.usado.is_(False),
            )
        )
        if data.correo and data.correo.strip():
            query = query.filter(usuarios.correo == data.correo.strip().lower())
        token_reg = query.order_by(tokens_usuario.id.desc()).first()

        if not token_reg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código de confirmación incorrecto",
            )
        usuario = (
            db.query(usuarios)
            .filter(usuarios.id_usuario == token_reg.id_usuario)
            .first()
        )
        if not usuario or not usuario.estado:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código de confirmación incorrecto",
            )
        if (
            token_reg.expira_en
            and token_reg.expira_en < datetime.now()
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="El código de confirmación ha expirado. Por favor solicita uno nuevo.",
            )
        usuario.verificado = True
        usuario.ultimo_acceso = datetime.now()
        token_reg.usado = True
        token_reg.fecha_uso = datetime.now()
        session_repository.commit(db)
    else:
        # Caso 2: Inicio de sesión por correo y contraseña
        if not data.correo or not data.contrasena:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Credenciales requeridas",
            )
        usuario = data_repository.queryVerifyCredentialsUsuario(db, data)
        password_hash = usuario.contrasena if usuario else _DUMMY_PASSWORD_HASH
        es_valido = verify_password(data.contrasena, password_hash)
        if not usuario or not usuario.estado or not es_valido:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales invalidas",
            )
        if getattr(usuario, "verificado", None) is False:
            client_ip = request.client.host if request.client else None
            nuevo_codigo = _crear_token_usuario(
                db, usuario.id_usuario, "verificacion", 30, client_ip
            )
            try:
                enviar_codigo_verificacion(
                    destinatario=usuario.correo,
                    nombre=usuario.nombre,
                    codigo=nuevo_codigo,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cuenta no verificada. Hemos enviado un nuevo código a tu correo.",
            )
        usuario.ultimo_acceso = datetime.now()
        session_repository.commit(db)

    # Obtener rol y datos del usuario antes del registro de log
    rol_obj = data_repository.queryVerifyCredentialsRolObj(db, usuario)
    rol_nombre = rol_obj.nombre if rol_obj else "agricultor"
    nombre_completo = (
        f"{usuario.nombre} {usuario.apellido}".strip()
        if usuario.apellido
        else usuario.nombre
    )
    user_id_str = str(usuario.id_usuario)
    user_email_str = usuario.correo
    user_nombre_str = usuario.nombre

    # Registrar log de inicio de sesión
    try:
        nuevo_log = logs_sistema(
            id_usuario=usuario.id_usuario,
            accion="login",
            modulo="auth",
            descripcion=f"Inicio de sesión exitoso: {user_nombre_str}",
        )
        session_repository.add(db, nuevo_log)
        session_repository.commit(db)
    except Exception as e:
        if db:
            db.rollback()
        logger.info(f"Error al registrar log: {e}")

    return {
        "id": user_id_str,
        "name": nombre_completo,
        "email": user_email_str,
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

    if (
        data.dni
        and data.dni.strip()
        and data.dni.strip() != (current_user.dni or "")
    ):
        dni_norm = data.dni.strip()
        dni_existente = (
            db.query(usuarios)
            .filter(
                usuarios.dni == dni_norm,
                usuarios.id_usuario != current_user.id_usuario,
            )
            .first()
        )
        if dni_existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El DNI ya está registrado por otro usuario",
            )
        current_user.dni = dni_norm
    elif data.dni is not None and not data.dni.strip():
        current_user.dni = None

    current_user.nombre = data.nombre.strip()
    current_user.apellido = data.apellido.strip() if data.apellido else None
    current_user.telefono = data.telefono.strip() if data.telefono else None
    if data.zona_horaria and data.zona_horaria.strip():
        current_user.zona_horaria = data.zona_horaria.strip()
    if data.fecha_nacimiento is not None:
        current_user.fecha_nacimiento = data.fecha_nacimiento
    if data.direccion is not None:
        current_user.direccion = (
            data.direccion.strip() if data.direccion.strip() else None
        )

    if data.contrasena and len(data.contrasena.strip()) > 0:
        current_user.contrasena = hash_password(data.contrasena)
        data_repository.queryActualizarPerfilAuthSessions(db, current_user)

    current_user.fecha_modificacion = datetime.now()

    session_repository.commit(db)
    session_repository.refresh(db, current_user)

    return {
        "success": True,
        "message": "Perfil actualizado con éxito",
        "name": current_user.nombre,
        "email": current_user.correo,
    }


def solicitar_recuperacion_contrasenaServ(
    request: Request, data: PasswordResetRequestInput, db: Session = None
):
    enforce_rate_limit(
        request, scope="password-reset-request", limit=5, window_seconds=600
    )
    correo_norm = str(data.correo).strip().lower()
    user = db.query(usuarios).filter(usuarios.correo == correo_norm).first()

    # Mensaje genérico para evitar enumeración de usuarios
    generic_msg = (
        "Si el correo está registrado, recibirás un código de recuperación."
    )

    if not user or not user.estado:
        return {
            "success": True,
            "message": generic_msg,
        }

    client_ip = request.client.host if request.client else None
    codigo_recuperacion = _crear_token_usuario(
        db, user.id_usuario, "recuperacion", 15, client_ip
    )

    try:
        enviar_codigo_recuperacion(
            destinatario=user.correo,
            nombre=user.nombre,
            codigo=codigo_recuperacion,
        )
    except Exception as e:
        logger.warning(f"Error al enviar código de recuperación: {e}")

    return {
        "success": True,
        "message": generic_msg,
    }


def restablecer_contrasenaServ(
    request: Request, data: PasswordResetConfirmInput, db: Session = None
):
    enforce_rate_limit(
        request, scope="password-reset-confirm", limit=10, window_seconds=600
    )
    correo_norm = str(data.correo).strip().lower()
    codigo_limpio = str(data.codigo).strip()

    user = db.query(usuarios).filter(usuarios.correo == correo_norm).first()
    if not user or not user.estado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de recuperación inválido o inexistente",
        )

    token_reg = (
        db.query(tokens_usuario)
        .filter(
            tokens_usuario.id_usuario == user.id_usuario,
            tokens_usuario.tipo == "recuperacion",
            tokens_usuario.token == codigo_limpio,
            tokens_usuario.usado.is_(False),
        )
        .order_by(tokens_usuario.id.desc())
        .first()
    )

    if not token_reg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código de recuperación inválido o inexistente",
        )

    if (
        token_reg.expira_en
        and token_reg.expira_en < datetime.now()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El código de recuperación ha expirado. Por favor, solicita uno nuevo.",
        )

    # Actualizar contraseña y marcar token
    user.contrasena = hash_password(data.nueva_contrasena)
    user.verificado = True
    user.fecha_modificacion = datetime.now()
    token_reg.usado = True
    token_reg.fecha_uso = datetime.now()

    # Revocar sesiones previas del usuario por seguridad
    try:
        data_repository.queryActualizarPerfilAuthSessions(db, user)
    except Exception as e:
        logger.warning(f"Error al revocar sesiones anteriores: {e}")

    # Registrar log de auditoría
    try:
        nuevo_log = logs_sistema(
            id_usuario=user.id_usuario,
            accion="recuperar_contrasena",
            modulo="auth",
            descripcion=f"Contraseña restablecida exitosamente para {user.correo}",
        )
        session_repository.add(db, nuevo_log)
    except Exception as e:
        logger.warning(f"Error al registrar log de recuperación de contraseña: {e}")

    session_repository.commit(db)

    return {
        "success": True,
        "message": "Tu contraseña ha sido restablecida exitosamente. Ya puedes iniciar sesión con tu nueva contraseña.",
    }

