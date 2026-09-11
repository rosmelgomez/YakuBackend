from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.dtos.ubicacionDto import (
    CultivoAdminResponse,
    CultivoCreate,
    CultivoResponseModel,
    DistritoCreate,
    DistritoResponseModel,
    FuenteAguaCreate,
    FuenteAguaResponseModel,
    ProvinciaCreate,
    ProvinciaResponseModel,
    RegionCreate,
    RegionResponseModel,
)
from src.main.service import ubicacionServ

router = APIRouter(prefix="/ubicacion", tags=["Ubicación Geográfica"])


@router.get("/regiones", response_model=List[RegionResponseModel])
def listar_regiones(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """Obtiene la lista de todas las regiones/departamentos disponibles."""
    return ubicacionServ.listar_regionesServ(db=db, current_user=current_user)


@router.get("/provincias/{id_region}", response_model=List[ProvinciaResponseModel])
def listar_provincias_por_region(
    id_region: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Obtiene la lista de provincias pertenecientes a una región específica."""
    return ubicacionServ.listar_provincias_por_regionServ(
        id_region=id_region, db=db, current_user=current_user
    )


@router.get("/distritos/{id_provincia}", response_model=List[DistritoResponseModel])
def listar_distritos_por_provincia(
    id_provincia: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Obtiene la lista de distritos pertenecientes a una provincia específica."""
    return ubicacionServ.listar_distritos_por_provinciaServ(
        id_provincia=id_provincia, db=db, current_user=current_user
    )


@router.get("/provincias", response_model=List[ProvinciaResponseModel])
def listar_todas_provincias(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """Obtiene la lista de todas las provincias registradas."""
    return ubicacionServ.listar_todas_provinciasServ(db=db, current_user=current_user)


@router.get("/distritos", response_model=List[DistritoResponseModel])
def listar_todos_distritos(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """Obtiene la lista de todos los distritos registrados."""
    return ubicacionServ.listar_todos_distritosServ(db=db, current_user=current_user)


@router.get("/fuentes-agua", response_model=List[FuenteAguaResponseModel])
def listar_fuentes_agua_usuario(
    id_usuario: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Obtiene la lista de fuentes de agua activas."""
    return ubicacionServ.listar_fuentes_agua_usuarioServ(
        id_usuario=id_usuario, db=db, current_user=current_user
    )


@router.get("/cultivos", response_model=List[CultivoAdminResponse])
def listar_cultivos_usuario(
    db: Session = Depends(get_db), current_user=Depends(get_current_user_or_bff)
):
    """Obtiene los cultivos del usuario autenticado, incluyendo su distrito y sector (lugar) asignados."""
    return ubicacionServ.listar_cultivos_usuarioServ(db=db, current_user=current_user)


@router.post(
    "/regiones", response_model=RegionResponseModel, status_code=status.HTTP_201_CREATED
)
def registrar_region(
    payload: RegionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Registra un nuevo departamento (región). Solo administradores."""
    return ubicacionServ.registrar_regionServ(
        payload=payload, db=db, current_user=current_user
    )


@router.post(
    "/provincias",
    response_model=ProvinciaResponseModel,
    status_code=status.HTTP_201_CREATED,
)
def registrar_provincia(
    payload: ProvinciaCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Registra una nueva provincia dentro de una región. Solo administradores."""
    return ubicacionServ.registrar_provinciaServ(
        payload=payload, db=db, current_user=current_user
    )


@router.post(
    "/distritos",
    response_model=DistritoResponseModel,
    status_code=status.HTTP_201_CREATED,
)
def registrar_distrito(
    payload: DistritoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Registra un nuevo distrito dentro de una provincia. Solo administradores."""
    return ubicacionServ.registrar_distritoServ(
        payload=payload, db=db, current_user=current_user
    )


@router.post(
    "/cultivos",
    response_model=CultivoResponseModel,
    status_code=status.HTTP_201_CREATED,
)
def registrar_cultivo(
    payload: CultivoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Registra un nuevo cultivo para el agricultor autenticado."""
    return ubicacionServ.registrar_cultivoServ(
        payload=payload, db=db, current_user=current_user
    )


@router.post(
    "/fuentes-agua",
    response_model=FuenteAguaResponseModel,
    status_code=status.HTTP_201_CREATED,
)
def registrar_fuente_agua(
    payload: FuenteAguaCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff),
):
    """Registra una nueva fuente de agua para el usuario autenticado."""
    return ubicacionServ.registrar_fuente_aguaServ(
        payload=payload, db=db, current_user=current_user
    )
