from typing import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..Auth.security import create_access_token, decode_access_token
from ..Model.conexion import SessionLocal
from ..Model.model import usuarios
from ..Model.schemas import AuthModel, TokenResponseModel, UsuarioTokenModel

router = APIRouter(prefix="/auth", tags=["Auth"])
bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> usuarios:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload.get("sub", "0"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido") from exc

    user = db.query(usuarios).filter(usuarios.id_usuario == user_id, usuarios.estado.is_(True)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o inactivo")

    return user


@router.post("/login", response_model=TokenResponseModel)
def login(data: AuthModel, db: Session = Depends(get_db)):
    user = (
        db.query(usuarios)
        .filter(
            (usuarios.correo == data.usuario) | (usuarios.nombre == data.usuario),
            usuarios.estado.is_(True),
        )
        .first()
    )

    if user is None or user.contrasena != data.contrasena:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    token = create_access_token(
        subject=str(user.id_usuario),
        extra_claims={"correo": user.correo, "nombre": user.nombre, "id_rol": user.id_rol},
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UsuarioTokenModel(
            id_usuario=user.id_usuario,
            nombre=user.nombre,
            correo=user.correo,
            id_rol=user.id_rol,
        ),
    }