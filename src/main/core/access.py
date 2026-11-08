from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.repositories import accessRep as data_repository


def require_assignment_access(db: Session, current_user, assignment_id: int):
    user_id = None if current_user.id_rol == 1 else current_user.id_usuario
    assignment = data_repository.queryAsignacion(db, assignment_id, user_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado"
        )
    return assignment


def require_crop_access(db: Session, current_user, crop_id: int):
    user_id = None if current_user.id_rol == 1 else current_user.id_usuario
    crop = data_repository.queryCultivo(db, crop_id, user_id)
    if not crop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado"
        )
    return crop


def require_telemetry_access(db: Session, current_user, telemetry_id: int):
    user_id = None if current_user.id_rol == 1 else current_user.id_usuario
    telemetry = data_repository.queryTelemetria(db, telemetry_id, user_id)
    if not telemetry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recurso no encontrado"
        )
    return telemetry


# ---------------------------------------------------------------------------
# Cultivos finalizados: solo se consulta su historial
# ---------------------------------------------------------------------------

MENSAJE_CULTIVO_FINALIZADO = (
    "El cultivo {nombre} está finalizado: ya no se puede regar ni operar sus "
    "sensores o actuadores. Su historial sigue disponible."
)


def _error_finalizado(nombre: str | None) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=MENSAJE_CULTIVO_FINALIZADO.format(nombre=nombre or ""),
    )


def require_cultivo_en_curso(db: Session, crop_id: int | None) -> None:
    """Bloquea riego, configuración y control sobre un cultivo finalizado."""
    if not crop_id:
        return
    from src.main.model.models import cultivos

    crop = db.query(cultivos).filter(cultivos.id_cultivo == crop_id).first()
    if crop is not None and crop.estado == "finalizado":
        raise _error_finalizado(crop.nombre_planta)


def require_dispositivo_operable(db: Session, dispositivo_id: int, current_user) -> None:
    """Un agricultor no puede encender, activar ni calibrar un equipo cuyo
    cultivo vigente está finalizado (el equipo ya volvió al stock). El
    administrador sí puede operarlo desde el inventario."""
    if getattr(current_user, "id_rol", None) == 1:
        return
    from src.main.model.models import dispositivos

    dev = db.query(dispositivos).filter(dispositivos.id_dispositivo == dispositivo_id).first()
    if dev is None:
        return
    vigentes = dev.asignaciones_vigentes
    cultivo = vigentes[0].cultivo if vigentes else None
    if cultivo is not None and cultivo.estado == "finalizado":
        raise _error_finalizado(cultivo.nombre_planta)
