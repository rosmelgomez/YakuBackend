import os
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from ..models.database import SessionLocal
from ..models.models import usuarios

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user_or_bff(
    request: Request,
    db: Session = Depends(get_db)
) -> usuarios:
    # 1. Intentar autenticación por BFF (si viene cabecera X-API-Key)
    x_api_key = request.headers.get("X-API-Key")
    if x_api_key:
        bff_key = os.getenv("FASTAPI_API_KEY", "clave_secreta_yaku_bff")
        if x_api_key != bff_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No autorizado: API Key del BFF inválida"
            )
            
        x_user_id = request.headers.get("X-User-Id")
        if not x_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Petición incorrecta: ID de usuario delegado ausente"
            )
            
        try:
            user_id = int(x_user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ID de usuario delegado inválido"
            )
            
        user = db.query(usuarios).filter(usuarios.id_usuario == user_id, usuarios.estado.is_(True)).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario delegado no encontrado o inactivo"
            )
        return user
    
    # 2. Si no es BFF, intentar autenticación estándar (JWT/Cookie)
    from .security import decode_access_token
    
    # Intentar leer desde cookies
    token = request.cookies.get("access_token")
    # Intentar leer desde Authorization header
    auth_header = request.headers.get("Authorization")
    if not token and auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ")[1]
        
    if token:
        try:
            payload = decode_access_token(token)
            if payload.get("type") == "access":
                user_id = int(payload.get("sub", "0"))
                user = db.query(usuarios).filter(usuarios.id_usuario == user_id, usuarios.estado.is_(True)).first()
                if user:
                    return user
        except Exception:
            pass
            
    # Intentar refresco silencioso automático mediante refresh token en cookies
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            payload = decode_access_token(refresh_token)
            if payload.get("type") == "refresh":
                user_id = int(payload.get("sub", "0"))
                user = db.query(usuarios).filter(usuarios.id_usuario == user_id, usuarios.estado.is_(True)).first()
                if user:
                    return user
        except Exception:
            pass

    # Si todo falla, levantar 401
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado o sesión expirada"
    )
