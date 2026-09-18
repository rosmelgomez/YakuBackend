"""CRUD y ejecución de horarios fijos de riego (HU-17)."""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.dtos.horarioDto import HorarioRiegoCreate, HorarioRiegoUpdate
from src.main.model.models import asignaciones_iot, horarios_riego
from src.main.repositories import sessionRep as session_repository

logger = logging.getLogger(__name__)


def _get_asignacion_o_403(db: Session, id_asignacion: int, current_user) -> asignaciones_iot:
    asig = db.query(asignaciones_iot).filter(asignaciones_iot.id == id_asignacion).first()
    if asig is None:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    if current_user.id_rol != 1 and asig.id_usuario != current_user.id_usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso sobre esta asignación.",
        )
    return asig


def _get_horario_o_403(db: Session, id_horario: int, current_user) -> horarios_riego:
    horario = db.query(horarios_riego).filter(horarios_riego.id == id_horario).first()
    if horario is None:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    if current_user.id_rol != 1 and horario.id_usuario != current_user.id_usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso sobre este horario.",
        )
    return horario


def crear_horarioServ(
    payload: HorarioRiegoCreate, db: Session = None, current_user=None
) -> horarios_riego:
    _get_asignacion_o_403(db, payload.id_asignacion, current_user)

    dias_invalidos = [d for d in payload.dias_semana if d < 0 or d > 6]
    if dias_invalidos:
        raise HTTPException(
            status_code=400, detail="Los días de la semana deben estar entre 0 y 6."
        )

    horario = horarios_riego(
        id_asignacion=payload.id_asignacion,
        id_usuario=current_user.id_usuario,
        hora_inicio=payload.hora_inicio,
        duracion_segundos=payload.duracion_segundos,
        dias_semana=payload.dias_semana,
        activo=payload.activo,
    )
    session_repository.add(db, horario)
    session_repository.commit(db)
    return horario


def listar_horariosServ(
    id_asignacion: int | None = None, db: Session = None, current_user=None
) -> list[horarios_riego]:
    query = db.query(horarios_riego)
    if current_user.id_rol != 1:
        query = query.filter(horarios_riego.id_usuario == current_user.id_usuario)
    if id_asignacion is not None:
        query = query.filter(horarios_riego.id_asignacion == id_asignacion)
    return query.order_by(horarios_riego.hora_inicio.asc()).all()


def actualizar_horarioServ(
    id_horario: int,
    payload: HorarioRiegoUpdate,
    db: Session = None,
    current_user=None,
) -> horarios_riego:
    horario = _get_horario_o_403(db, id_horario, current_user)

    if payload.dias_semana is not None:
        dias_invalidos = [d for d in payload.dias_semana if d < 0 or d > 6]
        if dias_invalidos:
            raise HTTPException(
                status_code=400,
                detail="Los días de la semana deben estar entre 0 y 6.",
            )
        horario.dias_semana = payload.dias_semana
    if payload.hora_inicio is not None:
        horario.hora_inicio = payload.hora_inicio
    if payload.duracion_segundos is not None:
        horario.duracion_segundos = payload.duracion_segundos
    if payload.activo is not None:
        horario.activo = payload.activo

    session_repository.add(db, horario)
    session_repository.commit(db)
    return horario


def eliminar_horarioServ(id_horario: int, db: Session = None, current_user=None) -> dict:
    horario = _get_horario_o_403(db, id_horario, current_user)
    session_repository.delete(db, horario)
    session_repository.commit(db)
    return {"status": "ok", "message": "Horario eliminado."}


def verificar_horarios_pendientesServ(db: Session) -> int:
    """Recorre los horarios activos y, si la hora/día actual coincide (con una
    ventana de tolerancia de 1 minuto) y no se ejecutó ya en el minuto en curso,
    inicia el riego programado. Se llama desde el ciclo del scheduler."""
    from src.main.service.irrigationServ import start_irrigation
    from src.main.repositories import controlRep as control_repo

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    dia_actual = now.weekday()  # 0=lunes ... 6=domingo
    iniciados = 0

    horarios = (
        db.query(horarios_riego).filter(horarios_riego.activo == True).all()  # noqa: E712
    )
    for horario in horarios:
        try:
            dias = horario.dias_semana or []
            if dias and dia_actual not in dias:
                continue

            hi = horario.hora_inicio
            coincide_hora = now.hour == hi.hour and now.minute == hi.minute
            if not coincide_hora:
                continue

            if (
                horario.ultima_ejecucion
                and horario.ultima_ejecucion.date() == now.date()
                and horario.ultima_ejecucion.hour == hi.hour
                and horario.ultima_ejecucion.minute == hi.minute
            ):
                continue  # ya ejecutado en este minuto/día

            asig = db.query(asignaciones_iot).filter(
                asignaciones_iot.id == horario.id_asignacion
            ).first()
            if not asig or not asig.activo:
                continue

            sesion_activa = control_repo.queryObtenerDatosControlSesionActiva(db, asig.id)
            tank_config = control_repo.queryObtenerDatosControlConfigT(db, asig)
            if sesion_activa or (tank_config and tank_config.bomba_encendida):
                continue

            start_irrigation(
                db=db,
                assignment=asig,
                irrigation_type="programado",
                requested_seconds=horario.duracion_segundos,
                now=now,
            )
            horario.ultima_ejecucion = now
            session_repository.add(db, horario)
            session_repository.commit(db)
            iniciados += 1
            logger.info(
                f"[HORARIOS] Riego programado iniciado para asignación {horario.id_asignacion} (horario {horario.id})."
            )
        except Exception:
            session_repository.rollback(db)
            logger.exception(f"Error ejecutando horario fijo {horario.id}")

    return iniciados
