from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from src.main.core.authDependencies import cookie_refresh_scheme, get_current_user
from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.authDto import (
    AuthModel,
    LoginResponseModel,
    UserRegisterInput,
    UserRegisterResponse,
    UserUpdateInput,
    UserVerifyResponse,
    VerifyCredentialsInput,
)
from src.main.dtos.usuarioDto import UsuarioResponseModel
from src.main.service import authServ

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponseModel)
def login(
    request: Request, response: Response, data: AuthModel, db: Session = Depends(get_db)
):
    return authServ.loginServ(request=request, response=response, data=data, db=db)


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Depends(cookie_refresh_scheme),
    db: Session = Depends(get_db),
):
    return authServ.refreshServ(
        request=request, response=response, refresh_token=refresh_token, db=db
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return authServ.logoutServ(
        request=request, response=response, current_user=current_user, db=db
    )


@router.post(
    "/register",
    response_model=UserRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    request: Request, data: UserRegisterInput, db: Session = Depends(get_db)
):
    return authServ.register_userServ(request=request, data=data, db=db)


@router.post("/verify-credentials", response_model=UserVerifyResponse)
def verify_credentials(
    request: Request, data: VerifyCredentialsInput, db: Session = Depends(get_db)
):
    return authServ.verify_credentialsServ(request=request, data=data, db=db)


@router.get("/perfil", response_model=UsuarioResponseModel)
def obtener_perfil(current_user=Depends(get_current_user_or_bff)):
    """
    Retorna el perfil completo del usuario autenticado.
    """
    return authServ.obtener_perfilServ(current_user=current_user)


@router.put("/perfil")
def actualizar_perfil(
    data: UserUpdateInput,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    return authServ.actualizar_perfilServ(data=data, db=db, current_user=current_user)
