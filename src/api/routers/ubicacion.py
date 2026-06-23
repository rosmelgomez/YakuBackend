from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db

from ...db.models import regiones, provincias, distritos, cultivos, fuentes_agua
from ...schemas.ubicacion import (
    RegionResponseModel, RegionCreate,
    ProvinciaResponseModel, ProvinciaCreate,
    DistritoResponseModel, DistritoCreate,
    CultivoResponseModel, CultivoCreate,
    FuenteAguaResponseModel, CultivoAdminResponse,
    FuenteAguaCreate
)
from ...core.bff_auth import get_current_user_or_bff

router = APIRouter(prefix="/ubicacion", tags=["Ubicación Geográfica"])


@router.get("/regiones", response_model=List[RegionResponseModel])
def listar_regiones(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Obtiene la lista de todas las regiones/departamentos disponibles."""
    return db.query(regiones).order_by(regiones.nombre.asc()).all()


@router.get("/provincias/{id_region}", response_model=List[ProvinciaResponseModel])
def listar_provincias_por_region(
    id_region: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Obtiene la lista de provincias pertenecientes a una región específica."""
    return db.query(provincias).filter(provincias.id_region == id_region).order_by(provincias.nombre.asc()).all()


@router.get("/distritos/{id_provincia}", response_model=List[DistritoResponseModel])
def listar_distritos_por_provincia(
    id_provincia: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Obtiene la lista de distritos pertenecientes a una provincia específica."""
    return db.query(distritos).filter(distritos.id_provincia == id_provincia).order_by(distritos.nombre.asc()).all()


@router.get("/provincias", response_model=List[ProvinciaResponseModel])
def listar_todas_provincias(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Obtiene la lista de todas las provincias registradas."""
    return db.query(provincias).order_by(provincias.nombre.asc()).all()


@router.get("/distritos", response_model=List[DistritoResponseModel])
def listar_todos_distritos(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Obtiene la lista de todos los distritos registrados."""
    return db.query(distritos).order_by(distritos.nombre.asc()).all()


@router.get("/fuentes-agua", response_model=List[FuenteAguaResponseModel])
def listar_fuentes_agua_usuario(
    id_usuario: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Obtiene la lista de fuentes de agua activas."""
    if current_user.id_rol != 1:
        id_usuario = current_user.id_usuario

    query = db.query(fuentes_agua).filter(fuentes_agua.activo == True)
    if id_usuario is not None:
        query = query.filter(fuentes_agua.id_usuario == id_usuario)

    return query.order_by(fuentes_agua.nombre.asc()).all()


@router.get("/cultivos", response_model=List[CultivoAdminResponse])
def listar_cultivos_usuario(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Obtiene los cultivos del usuario autenticado, incluyendo su distrito y sector (lugar) asignados."""
    # Si es administrador (rol 1), listar todos los cultivos. De lo contrario, filtrar por el usuario logueado.
    if current_user.id_rol == 1:
        return db.query(cultivos).order_by(cultivos.id_cultivo.desc()).all()
    return db.query(cultivos).filter(cultivos.id_usuario == current_user.id_usuario).order_by(cultivos.id_cultivo.desc()).all()


@router.post("/regiones", response_model=RegionResponseModel, status_code=status.HTTP_201_CREATED)
def registrar_region(
    payload: RegionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Registra un nuevo departamento (región). Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción."
        )
    
    # Verificar si existe duplicado
    existente = db.query(regiones).filter(regiones.nombre == payload.nombre).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El departamento ya se encuentra registrado."
        )
        
    nueva = regiones(nombre=payload.nombre)
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.post("/provincias", response_model=ProvinciaResponseModel, status_code=status.HTTP_201_CREATED)
def registrar_provincia(
    payload: ProvinciaCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Registra una nueva provincia dentro de una región. Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador."
        )
    
    # Verificar si la región existe
    region_existente = db.query(regiones).filter(regiones.id == payload.id_region).first()
    if not region_existente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La región especificada no existe."
        )

    # Verificar si existe duplicado en la misma región
    existente = db.query(provincias).filter(
        provincias.id_region == payload.id_region,
        provincias.nombre == payload.nombre
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La provincia ya se encuentra registrada en esta región."
        )

    nueva = provincias(id_region=payload.id_region, nombre=payload.nombre)
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.post("/distritos", response_model=DistritoResponseModel, status_code=status.HTTP_201_CREATED)
def registrar_distrito(
    payload: DistritoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Registra un nuevo distrito dentro de una provincia. Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador."
        )
    
    # Verificar si la provincia existe
    provincia_existente = db.query(provincias).filter(provincias.id == payload.id_provincia).first()
    if not provincia_existente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La provincia especificada no existe."
        )

    # Verificar duplicado
    existente = db.query(distritos).filter(
        distritos.id_provincia == payload.id_provincia,
        distritos.nombre == payload.nombre
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El distrito ya se encuentra registrado en esta provincia."
        )

    nueva = distritos(id_provincia=payload.id_provincia, nombre=payload.nombre)
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@router.post("/cultivos", response_model=CultivoResponseModel, status_code=status.HTTP_201_CREATED)
def registrar_cultivo(
    payload: CultivoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Registra un nuevo cultivo para el agricultor autenticado."""
    fecha_siembra_parsed = None
    if payload.fecha_siembra:
        try:
            fecha_siembra_parsed = datetime.strptime(payload.fecha_siembra, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de fecha inválido. Utilice AAAA-MM-DD."
            )

    nuevo = cultivos(
        id_usuario=current_user.id_usuario,
        id_planta=payload.id_planta,
        id_fuente_agua=payload.id_fuente_agua,
        id_distrito=payload.id_distrito,
        lugar=payload.lugar,
        nombre_planta=payload.nombre_planta,
        etapa_crecimiento=payload.etapa_crecimiento,
        area_m2=payload.area_m2,
        fecha_siembra=fecha_siembra_parsed,
        estado="activo"
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.post("/fuentes-agua", response_model=FuenteAguaResponseModel, status_code=status.HTTP_201_CREATED)
def registrar_fuente_agua(
    payload: FuenteAguaCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_or_bff)
):
    """Registra una nueva fuente de agua para el usuario autenticado."""
    if payload.tipo == 'tanque':
        if payload.capacidad_litros is None or payload.altura_tanque_cm is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Para un tanque, la capacidad en litros y la altura del tanque son obligatorias."
            )
    elif payload.tipo == 'manguera':
        payload.capacidad_litros = None
        payload.altura_tanque_cm = None
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de fuente de agua inválido. Debe ser 'tanque' o 'manguera'."
        )

    # Por defecto 10cm si no se especifica altura de seguridad
    altura_seg = payload.altura_seguridad_cm if payload.altura_seguridad_cm is not None else 10.0

    nueva = fuentes_agua(
        id_usuario=current_user.id_usuario,
        nombre=payload.nombre,
        tipo=payload.tipo,
        capacidad_litros=payload.capacidad_litros,
        altura_tanque_cm=payload.altura_tanque_cm,
        altura_seguridad_cm=altura_seg,
        activo=True
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva
