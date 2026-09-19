from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from src.main.core.authDependencies import cookie_refresh_scheme, get_current_user
from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.authDto import (
    AuthModel,
    LoginResponseModel,
    PasswordResetConfirmInput,
    PasswordResetRequestInput,
    PasswordResetResponse,
    ResendCodeInput,
    ResendCodeResponse,
    UserRegisterInput,
    UserRegisterResponse,
    UserUpdateInput,
    UserVerifyResponse,
    VerifyCredentialsInput,
    VerifyTokenInput,
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
    request: Request, response: Response, data: VerifyCredentialsInput, db: Session = Depends(get_db)
):
    return authServ.verify_credentialsServ(request=request, response=response, data=data, db=db)


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


@router.post("/reenviar-codigo", response_model=ResendCodeResponse)
def reenviar_codigo(
    request: Request, data: ResendCodeInput, db: Session = Depends(get_db)
):
    """
    Reenvía un nuevo código de confirmación de 6 dígitos al correo especificado.
    """
    return authServ.reenviar_codigo_verificacionServ(
        request=request, data=data, db=db
    )


@router.post("/verificar-correo")
def verificar_correo(
    data: VerifyTokenInput, db: Session = Depends(get_db)
):
    """
    Verifica el correo electrónico de un usuario mediante el token o código recibido.
    """
    return authServ.verificar_tokenServ(token=data.token, correo=data.correo, db=db)


@router.get("/verificar-correo/{token}")
def verificar_correo_get(
    token: str, db: Session = Depends(get_db)
):
    """
    Verifica el correo electrónico de un usuario mediante GET con el token en la ruta.
    """
    return authServ.verificar_tokenServ(token=token, db=db)


@router.post(
    "/recuperar-contrasena/solicitar",
    response_model=PasswordResetResponse,
)
def solicitar_recuperacion_contrasena(
    request: Request,
    data: PasswordResetRequestInput,
    db: Session = Depends(get_db),
):
    """
    Solicita el envío de un código de 6 dígitos al correo para recuperar la contraseña.
    """
    return authServ.solicitar_recuperacion_contrasenaServ(
        request=request, data=data, db=db
    )


@router.post(
    "/recuperar-contrasena/restablecer",
    response_model=PasswordResetResponse,
)
def restablecer_contrasena(
    request: Request,
    data: PasswordResetConfirmInput,
    db: Session = Depends(get_db),
):
    """
    Restablece la contraseña del usuario validando el código de 6 dígitos.
    """
    return authServ.restablecer_contrasenaServ(
        request=request, data=data, db=db
    )



