from datetime import datetime
import hashlib
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, field_validator

logger = logging.getLogger(__name__)

from ...core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    verify_password,
    hash_password,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from ...core.bff_auth import get_current_user_or_bff
from ...db.models import auth_sessions, usuarios, roles, logs_sistema
from ...core.config import COOKIE_SECURE
from ...core.rate_limit import enforce_rate_limit
from ...schemas.auth import (
    AuthModel, LoginResponseModel, UsuarioTokenModel,
    UserRegisterInput, UserRegisterResponse, VerifyCredentialsInput, UserVerifyResponse,
    UsuarioResponseModel
)
from ..dependencies import get_db

router = APIRouter(prefix="/auth", tags=["Auth"])
cookie_scheme = APIKeyCookie(name="access_token", auto_error=False)
cookie_refresh_scheme = APIKeyCookie(name="refresh_token", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)
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
    cookie_token: str | None = Depends(cookie_scheme),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
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

    user = db.query(usuarios).filter(usuarios.id_usuario == user_id, usuarios.estado.is_(True)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo",
        )

    return user


@router.post("/login", response_model=LoginResponseModel)
def login(
    request: Request,
    response: Response,
    data: AuthModel,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, scope="login", limit=5, window_seconds=300)
    user = (
        db.query(usuarios)
        .filter(
            (usuarios.correo == data.usuario) | (usuarios.nombre == data.usuario),
            usuarios.estado.is_(True),
        )
        .first()
    )

    password_hash = user.contrasena if user else _DUMMY_PASSWORD_HASH
    if not verify_password(data.contrasena, password_hash) or user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    access_token = create_access_token(
        subject=str(user.id_usuario),
        extra_claims={"correo": user.correo, "nombre": user.nombre, "id_rol": user.id_rol},
    )
    refresh_token, refresh_session = _new_refresh_token(user)
    db.add(refresh_session)
    db.commit()

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


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Depends(cookie_refresh_scheme),
    db: Session = Depends(get_db),
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
            raise ValueError("El token proporcionado no es un token de actualización válido")
        user_id = int(payload.get("sub", "0"))
        session_id = str(payload.get("sid", ""))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de actualización inválido o expirado",
        ) from exc

    user = db.query(usuarios).filter(usuarios.id_usuario == user_id, usuarios.estado.is_(True)).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o inactivo",
        )

    stored_session = db.query(auth_sessions).filter(
        auth_sessions.session_id == session_id,
        auth_sessions.id_usuario == user_id,
        auth_sessions.token_hash == _token_hash(refresh_token),
        auth_sessions.revoked.is_(False),
    ).first()
    if not stored_session or stored_session.expires_at <= datetime.now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion expirada o revocada")
    stored_session.revoked = True
    stored_session.revoked_at = datetime.now()

    new_access_token = create_access_token(
        subject=str(user.id_usuario),
        extra_claims={"correo": user.correo, "nombre": user.nombre, "id_rol": user.id_rol},
    )

    new_refresh_token, new_refresh_session = _new_refresh_token(user)
    db.add(new_refresh_session)
    db.commit()

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


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = decode_access_token(refresh_token)
            session_id = str(payload.get("sid", ""))
            stored_session = db.query(auth_sessions).filter(
                auth_sessions.session_id == session_id,
                auth_sessions.id_usuario == current_user.id_usuario,
            ).first()
            if stored_session:
                stored_session.revoked = True
                stored_session.revoked_at = datetime.now()
                db.commit()
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


@router.post("/register", response_model=UserRegisterResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    request: Request,
    data: UserRegisterInput,
    db: Session = Depends(get_db)
):
    enforce_rate_limit(request, scope="register", limit=3, window_seconds=3600)
    # 1. Validar si el usuario ya existe
    usuario_existente = db.query(usuarios).filter(usuarios.correo == data.correo).first()
    if usuario_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya está registrado"
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
        estado=True
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    return {
        "success": True,
        "message": "Usuario registrado con éxito",
        "userId": nuevo_usuario.id_usuario
    }


@router.post("/verify-credentials", response_model=UserVerifyResponse)
def verify_credentials(
    request: Request,
    data: VerifyCredentialsInput,
    db: Session = Depends(get_db)
):
    enforce_rate_limit(request, scope="verify-credentials", limit=5, window_seconds=300)
    # 1. Buscar usuario
    usuario = db.query(usuarios).filter(usuarios.correo == data.correo).first()
    password_hash = usuario.contrasena if usuario else _DUMMY_PASSWORD_HASH
    es_valido = verify_password(data.contrasena, password_hash)
    if not usuario or not usuario.estado or not es_valido:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas"
        )

    # 3. Registrar log de inicio de sesión
    try:
        nuevo_log = logs_sistema(
            id_usuario=usuario.id_usuario,
            accion="login",
            modulo="auth",
            descripcion=f"Inicio de sesión exitoso: {usuario.nombre}"
        )
        db.add(nuevo_log)
        db.commit()
    except Exception as e:
        logger.info(f"Error al registrar log: {e}")

    # 4. Obtener rol
    rol_obj = db.query(roles).filter(roles.id_rol == usuario.id_rol).first()
    rol_nombre = rol_obj.nombre if rol_obj else "agricultor"

    return {
        "id": str(usuario.id_usuario),
        "name": usuario.nombre,
        "email": usuario.correo,
        "rol": rol_nombre
    }


class UserUpdateInput(BaseModel):
    nombre: str = Field(min_length=2, max_length=100)
    apellido: str | None = Field(default=None, max_length=100)
    correo: EmailStr
    telefono: str | None = Field(default=None, max_length=20)
    contrasena: str | None = Field(default=None, min_length=10, max_length=128)

    @field_validator("contrasena")
    @classmethod
    def validate_optional_password(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not any(char.islower() for char in value) or not any(char.isupper() for char in value):
            raise ValueError("La contrasena debe incluir mayusculas y minusculas")
        if not any(char.isdigit() for char in value):
            raise ValueError("La contrasena debe incluir al menos un numero")
        return value

@router.get("/perfil", response_model=UsuarioResponseModel)
def obtener_perfil(
    current_user=Depends(get_current_user_or_bff),
):
    """
    Retorna el perfil completo del usuario autenticado.
    """
    return current_user

@router.put("/perfil")
def actualizar_perfil(
    data: UserUpdateInput,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    # 1. Si cambia de correo, validar que no esté tomado por otro usuario
    if data.correo != current_user.correo:
        correo_existente = db.query(usuarios).filter(
            usuarios.correo == data.correo, 
            usuarios.id_usuario != current_user.id_usuario
        ).first()
        if correo_existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo ya está registrado por otro usuario"
            )
        current_user.correo = str(data.correo).lower()

    current_user.nombre = data.nombre
    current_user.apellido = data.apellido
    current_user.telefono = data.telefono
    
    if data.contrasena and len(data.contrasena.strip()) > 0:
        current_user.contrasena = hash_password(data.contrasena)
        db.query(auth_sessions).filter(
            auth_sessions.id_usuario == current_user.id_usuario,
            auth_sessions.revoked.is_(False),
        ).update({"revoked": True, "revoked_at": datetime.now()})
        
    db.commit()
    db.refresh(current_user)
    
    return {
        "success": True,
        "message": "Perfil actualizado con éxito",
        "name": current_user.nombre,
        "email": current_user.correo
    }
