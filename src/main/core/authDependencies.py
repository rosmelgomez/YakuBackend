"""Dependencias HTTP para autenticar sesiones de Yaku."""

from fastapi import Depends
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.main.db.databaseSession import get_db
from src.main.service import authServ

cookie_scheme = APIKeyCookie(name="access_token", auto_error=False)
cookie_refresh_scheme = APIKeyCookie(name="refresh_token", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    cookie_token: str | None = Depends(cookie_scheme),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    return authServ.get_current_user(
        cookie_token=cookie_token, credentials=credentials, db=db
    )
