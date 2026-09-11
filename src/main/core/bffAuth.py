from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.main.core.bffTokens import decode_bff_token
from src.main.db.databaseSession import get_db
from src.main.model.models import usuarios
from src.main.repositories import bffAuthRep as data_repository


def _active_user(db: Session, user_id: int) -> usuarios | None:
    return data_repository.queryActiveUserResultado(db, user_id)


def get_current_user_or_bff(
    request: Request,
    db: Session = Depends(get_db),
) -> usuarios:
    bff_token = request.headers.get("X-BFF-Token")
    if bff_token:
        try:
            payload = decode_bff_token(bff_token, audience="yaku-api")
            user = _active_user(db, int(payload["sub"]))
        except (ValueError, TypeError):
            user = None
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token BFF invalido o vencido",
            )
        return user

    from src.main.core.security import decode_access_token

    token = request.cookies.get("access_token")
    auth_header = request.headers.get("Authorization")
    if not token and auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]

    if token:
        try:
            payload = decode_access_token(token)
            if payload.get("type") == "access":
                user = _active_user(db, int(payload.get("sub", "0")))
                if user:
                    return user
        except (ValueError, TypeError):
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado o sesion expirada",
    )
