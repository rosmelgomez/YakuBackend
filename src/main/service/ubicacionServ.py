from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.dtos.ubicacionDto import (
    CultivoCreate,
    DistritoCreate,
    FuenteAguaCreate,
    ProvinciaCreate,
    RegionCreate,
)
from src.main.model.models import (
    cultivos,
    distritos,
    fuentes_agua,
    provincias,
    regiones,
)
from src.main.repositories import sessionRep as session_repository
from src.main.repositories import ubicacionRep as data_repository


def listar_regionesServ(db: Session = None, current_user=None):
    """Obtiene la lista de todas las regiones/departamentos disponibles."""
    return data_repository.queryListarRegionesResultado(db)


def listar_provincias_por_regionServ(
    id_region: int, db: Session = None, current_user=None
):
    """Obtiene la lista de provincias pertenecientes a una región específica."""
    return data_repository.queryListarProvinciasPorRegionResultado(db, id_region)


def listar_distritos_por_provinciaServ(
    id_provincia: int, db: Session = None, current_user=None
):
    """Obtiene la lista de distritos pertenecientes a una provincia específica."""
    return data_repository.queryListarDistritosPorProvinciaResultado(db, id_provincia)


def listar_todas_provinciasServ(db: Session = None, current_user=None):
    """Obtiene la lista de todas las provincias registradas."""
    return data_repository.queryListarTodasProvinciasResultado(db)


def listar_todos_distritosServ(db: Session = None, current_user=None):
    """Obtiene la lista de todos los distritos registrados."""
    return data_repository.queryListarTodosDistritosResultado(db)


def listar_fuentes_agua_usuarioServ(
    id_usuario: int | None = None, db: Session = None, current_user=None
):
    """Obtiene la lista de fuentes de agua activas."""
    if current_user.id_rol != 1:
        id_usuario = current_user.id_usuario

    query = data_repository.queryListarFuentesAguaUsuarioQuery(db)
    if id_usuario is not None:
        query = data_repository.queryListarFuentesAguaUsuarioQuery2(query, id_usuario)

    return data_repository.queryListarFuentesAguaUsuarioResultado(query)


def listar_cultivos_usuarioServ(db: Session = None, current_user=None):
    """Obtiene los cultivos del usuario autenticado, incluyendo su distrito y sector (lugar) asignados."""
    # Si es administrador (rol 1), listar todos los cultivos. De lo contrario, filtrar por el usuario logueado.
    if current_user.id_rol == 1:
        return data_repository.queryListarCultivosUsuarioResultado(db)
    return data_repository.queryListarCultivosUsuarioResultado2(db, current_user)


def registrar_regionServ(payload: RegionCreate, db: Session = None, current_user=None):
    """Registra un nuevo departamento (región). Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    # Verificar si existe duplicado
    existente = data_repository.queryRegistrarRegionExistente(db, payload)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El departamento ya se encuentra registrado.",
        )

    nueva = regiones(nombre=payload.nombre)
    session_repository.add(db, nueva)
    session_repository.commit(db)
    session_repository.refresh(db, nueva)
    return nueva


def registrar_provinciaServ(
    payload: ProvinciaCreate, db: Session = None, current_user=None
):
    """Registra una nueva provincia dentro de una región. Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador.",
        )

    # Verificar si la región existe
    region_existente = data_repository.queryRegistrarProvinciaRegionExistente(
        db, payload
    )
    if not region_existente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La región especificada no existe.",
        )

    # Verificar si existe duplicado en la misma región
    existente = data_repository.queryRegistrarProvinciaExistente(db, payload)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La provincia ya se encuentra registrada en esta región.",
        )

    nueva = provincias(id_region=payload.id_region, nombre=payload.nombre)
    session_repository.add(db, nueva)
    session_repository.commit(db)
    session_repository.refresh(db, nueva)
    return nueva


def registrar_distritoServ(
    payload: DistritoCreate, db: Session = None, current_user=None
):
    """Registra un nuevo distrito dentro de una provincia. Solo administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador.",
        )

    # Verificar si la provincia existe
    provincia_existente = data_repository.queryRegistrarDistritoProvinciaExistente(
        db, payload
    )
    if not provincia_existente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La provincia especificada no existe.",
        )

    # Verificar duplicado
    existente = data_repository.queryRegistrarDistritoExistente(db, payload)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El distrito ya se encuentra registrado en esta provincia.",
        )

    nueva = distritos(id_provincia=payload.id_provincia, nombre=payload.nombre)
    session_repository.add(db, nueva)
    session_repository.commit(db)
    session_repository.refresh(db, nueva)
    return nueva


def registrar_cultivoServ(
    payload: CultivoCreate, db: Session = None, current_user=None
):
    """Registra un nuevo cultivo para el agricultor autenticado."""
    fecha_siembra_parsed = None
    if payload.fecha_siembra:
        try:
            fecha_siembra_parsed = datetime.strptime(
                payload.fecha_siembra, "%Y-%m-%d"
            ).date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de fecha inválido. Utilice AAAA-MM-DD.",
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
        estado="activo",
    )
    session_repository.add(db, nuevo)
    session_repository.commit(db)
    session_repository.refresh(db, nuevo)
    return nuevo


def registrar_fuente_aguaServ(
    payload: FuenteAguaCreate, db: Session = None, current_user=None
):
    """Registra una nueva fuente de agua para el usuario autenticado."""
    nueva = fuentes_agua(
        id_usuario=current_user.id_usuario,
        nombre=payload.nombre,
        tipo=payload.tipo,
        capacidad_litros=payload.capacidad_litros,
        altura_tanque_cm=payload.altura_tanque_cm,
        altura_seguridad_cm=payload.altura_seguridad_cm,
        activo=True,
    )
    session_repository.add(db, nueva)
    session_repository.commit(db)
    session_repository.refresh(db, nueva)
    return nueva
