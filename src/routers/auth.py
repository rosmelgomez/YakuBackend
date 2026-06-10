from typing import Generator

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    verify_password,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from ..models.database import SessionLocal
from ..models.models import usuarios
from ..schemas.schemas import AuthModel, LoginResponseModel, UsuarioTokenModel

router = APIRouter(prefix="/auth", tags=["Auth"])
cookie_scheme = APIKeyCookie(name="access_token", auto_error=False)
cookie_refresh_scheme = APIKeyCookie(name="refresh_token", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    response: Response,
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
    token_valid = False

    if token:
        try:
            payload = decode_access_token(token)
            if payload.get("type") == "access":
                user_id = int(payload.get("sub", "0"))
                token_valid = True
        except Exception:
            token_valid = False

    # Refresco automático silencioso si el access token no es válido o no está presente
    if not token_valid:
        refresh_token = request.cookies.get("refresh_token")
        if refresh_token:
            try:
                payload = decode_access_token(refresh_token)
                if payload.get("type") == "refresh":
                    user_id = int(payload.get("sub", "0"))
                    
                    user = db.query(usuarios).filter(usuarios.id_usuario == user_id, usuarios.estado.is_(True)).first()
                    if user:
                        # Generar nuevo access token
                        new_access_token = create_access_token(
                            subject=str(user.id_usuario),
                            extra_claims={"correo": user.correo, "nombre": user.nombre, "id_rol": user.id_rol},
                        )
                        is_secure = request.url.scheme == "https"
                        # Escribir la cookie httponly de acceso
                        response.set_cookie(
                            key="access_token",
                            value=new_access_token,
                            httponly=True,
                            secure=is_secure,
                            samesite="lax",
                            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                        )
                        return user
            except Exception:
                pass

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
    user = (
        db.query(usuarios)
        .filter(
            (usuarios.correo == data.usuario) | (usuarios.nombre == data.usuario),
            usuarios.estado.is_(True),
        )
        .first()
    )

    if user is None or not verify_password(data.contrasena, user.contrasena):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    access_token = create_access_token(
        subject=str(user.id_usuario),
        extra_claims={"correo": user.correo, "nombre": user.nombre, "id_rol": user.id_rol},
    )
    refresh_token = create_refresh_token(
        subject=str(user.id_usuario),
        extra_claims={"correo": user.correo, "nombre": user.nombre, "id_rol": user.id_rol},
    )

    # Determinar si la conexión es HTTPS de forma dinámica para desarrollo local (HTTP)
    is_secure = request.url.scheme == "https"

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

    # Generamos un nuevo Access Token
    new_access_token = create_access_token(
        subject=str(user.id_usuario),
        extra_claims={"correo": user.correo, "nombre": user.nombre, "id_rol": user.id_rol},
    )

    is_secure = request.url.scheme == "https"

    # Establecemos la nueva cookie del Access Token
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return {"status": "ok", "message": "Token renovado exitosamente"}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
):
    is_secure = request.url.scheme == "https"
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