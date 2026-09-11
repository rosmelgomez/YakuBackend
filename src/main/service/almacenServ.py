from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.dtos.almacenDto import AlmacenCreate
from src.main.model.models import almacenes
from src.main.repositories import almacenRep as data_repository
from src.main.repositories import sessionRep as session_repository


def listar_almacenesServ(db: Session = None, current_user=None):
    """Obtiene el listado completo de almacenes."""
    return data_repository.queryListarAlmacenesResultado(db)


def registrar_almacenServ(
    payload: AlmacenCreate, db: Session = None, current_user=None
):
    """Registra un nuevo almacén. Solo accesible por administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    # Validar duplicados
    existente = data_repository.queryRegistrarAlmacenExistente(db, payload)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un almacén con este nombre.",
        )

    nuevo = almacenes(
        nombre=payload.nombre,
        id_distrito=payload.id_distrito,
        direccion=payload.direccion,
    )
    session_repository.add(db, nuevo)
    session_repository.commit(db)
    session_repository.refresh(db, nuevo)
    return nuevo


def eliminar_almacenServ(almacen_id: int, db: Session = None, current_user=None):
    """Elimina un almacén si no tiene dispositivos ni componentes asignados. Solo accesible por administradores."""
    if current_user.id_rol != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador para realizar esta acción.",
        )

    alm = data_repository.queryEliminarAlmacenAlm(db, almacen_id)
    if not alm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Almacén no encontrado."
        )

    # Verificar si tiene dispositivos en stock
    tiene_dispositivos = data_repository.queryEliminarAlmacenTieneDispositivos(
        db, almacen_id
    )
    if tiene_dispositivos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar el almacén porque contiene dispositivos asociados.",
        )

    # Verificar si tiene componentes en stock
    tiene_componentes = data_repository.queryEliminarAlmacenTieneComponentes(
        db, almacen_id
    )
    if tiene_componentes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar el almacén porque contiene componentes asociados.",
        )

    session_repository.delete(db, alm)
    session_repository.commit(db)
    return {"status": "ok", "message": "Almacén eliminado correctamente."}
