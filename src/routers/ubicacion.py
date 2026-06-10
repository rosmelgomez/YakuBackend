from typing import Generator, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..models.database import SessionLocal
from ..models.models import regiones, provincias, distritos, cultivos
from ..schemas.schemas import RegionResponseModel, ProvinciaResponseModel, DistritoResponseModel, CultivoResponseModel
from .auth import get_current_user

router = APIRouter(prefix="/ubicacion", tags=["Ubicación Geográfica"])

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/regiones", response_model=List[RegionResponseModel])
def listar_regiones(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Obtiene la lista de todas las regiones/departamentos disponibles."""
    return db.query(regiones).order_by(regiones.nombre.asc()).all()


@router.get("/provincias/{id_region}", response_model=List[ProvinciaResponseModel])
def listar_provincias_por_region(
    id_region: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Obtiene la lista de provincias pertenecientes a una región específica."""
    return db.query(provincias).filter(provincias.id_region == id_region).order_by(provincias.nombre.asc()).all()


@router.get("/distritos/{id_provincia}", response_model=List[DistritoResponseModel])
def listar_distritos_por_provincia(
    id_provincia: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Obtiene la lista de distritos pertenecientes a una provincia específica."""
    return db.query(distritos).filter(distritos.id_provincia == id_provincia).order_by(distritos.nombre.asc()).all()


@router.get("/cultivos", response_model=List[CultivoResponseModel])
def listar_cultivos_usuario(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Obtiene los cultivos del usuario autenticado, incluyendo su distrito y sector (lugar) asignados."""
    # Si es administrador (rol 1), listar todos los cultivos. De lo contrario, filtrar por el usuario logueado.
    if current_user.id_rol == 1:
        return db.query(cultivos).order_by(cultivos.id_cultivo.desc()).all()
    return db.query(cultivos).filter(cultivos.id_usuario == current_user.id_usuario).order_by(cultivos.id_cultivo.desc()).all()
