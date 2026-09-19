"""CRUD y ejecución de horarios fijos de riego (HU-17)."""

import logging
from datetime import datetime, time, timezone

import pytz
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.dtos.horarioDto import HorarioRiegoCreate, HorarioRiegoUpdate
from src.main.model.models import asignaciones_iot, horarios_riego
from src.main.repositories import sessionRep as session_repository

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "America/Lima"


def _get_timezone(zona_horaria: str | None):
    try:
        return pytz.timezone(zona_horaria or DEFAULT_TIMEZONE)
    except pytz.UnknownTimeZoneError:
        return pytz.timezone(DEFAULT_TIMEZONE)

DURACION_MAX_SEGUNDOS = 3600  # 1 hora, mismo tope que antes se pedia como dato de entrada
SEGUNDOS_POR_DIA = 24 * 3600


def _calcular_duracion_segundos(hora_inicio: time, hora_fin: time) -> int:
    """Calcula la duracion del riego a partir del rango "de hora a hora" que
    ingresa el usuario. Soporta rangos que cruzan la medianoche: si hora_fin
    es menor o igual a hora_inicio, se asume que termina al dia siguiente
    (ej. 23:50 -> 00:10 dura 20 minutos), salvo que ambas horas sean iguales,
    lo cual se rechaza por ser una duracion nula/ambigua."""
    inicio_seg = hora_inicio.hour * 3600 + hora_inicio.minute * 60 + hora_inicio.second
    fin_seg = hora_fin.hour * 3600 + hora_fin.minute * 60 + hora_fin.second

    if fin_seg == inicio_seg:
        raise HTTPException(
            status_code=400,
            detail="La hora de fin no puede ser igual a la hora de inicio.",
        )

    duracion = fin_seg - inicio_seg
    if duracion < 0:
        duracion += SEGUNDOS_POR_DIA  # el rango cruza la medianoche

    if duracion > DURACION_MAX_SEGUNDOS:
        raise HTTPException(
            status_code=400,
            detail=f"El rango de riego no puede superar {DURACION_MAX_SEGUNDOS // 60} minutos.",
        )
    return duracion


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

    if payload.siempre_activo:
        hora_inicio = hora_fin = None
        duracion_segundos = None
    else:
        hora_inicio = payload.hora_inicio
        hora_fin = payload.hora_fin
        duracion_segundos = _calcular_duracion_segundos(hora_inicio, hora_fin)

    horario = horarios_riego(
        id_asignacion=payload.id_asignacion,
        id_usuario=current_user.id_usuario,
        siempre_activo=payload.siempre_activo,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        duracion_segundos=duracion_segundos,
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
    return query.order_by(
        horarios_riego.siempre_activo.desc(), horarios_riego.hora_inicio.asc()
    ).all()


def tiene_horario_configuradoServ(db: Session, id_asignacion: int) -> bool:
    """Indica si la asignación (actuador de riego) tiene al menos un horario
    configurado — de franja fija o "siempre activo" —, sin importar si está
    activo o pausado en este momento. Se usa como requisito previo para
    habilitar el riego automático (IA o programado)."""
    return (
        db.query(horarios_riego)
        .filter(horarios_riego.id_asignacion == id_asignacion)
        .first()
        is not None
    )


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
    if payload.siempre_activo is not None:
        horario.siempre_activo = payload.siempre_activo
    if payload.hora_inicio is not None:
        horario.hora_inicio = payload.hora_inicio
    if payload.hora_fin is not None:
        horario.hora_fin = payload.hora_fin

    if horario.siempre_activo:
        # Sin franja fija: la IA evalua continuamente, no hace falta hora/duracion.
        horario.hora_inicio = None
        horario.hora_fin = None
        horario.duracion_segundos = None
    else:
        # Si se acaba de desactivar "siempre activo" o se tocó alguna hora,
        # ambas horas son obligatorias para poder recalcular la duración.
        tocó_horas = payload.hora_inicio is not None or payload.hora_fin is not None
        dejó_de_ser_continuo = payload.siempre_activo is False
        if tocó_horas or dejó_de_ser_continuo:
            if not horario.hora_inicio or not horario.hora_fin:
                raise HTTPException(
                    status_code=400,
                    detail="Debe indicar hora_inicio y hora_fin (o mantener siempre_activo).",
                )
            horario.duracion_segundos = _calcular_duracion_segundos(
                horario.hora_inicio, horario.hora_fin
            )

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
    inicia el riego programado. Se llama desde el ciclo del scheduler.

    `hora_inicio` se guarda tal como el usuario la escribió en su navegador
    (hora LOCAL de su zona horaria, ej. "22:00" para las 10pm), por lo que la
    comparación se hace contra la hora actual en la zona horaria del dueño del
    horario (`usuarios.zona_horaria`), no contra UTC. De lo contrario, un
    horario nocturno para un usuario en America/Lima (UTC-5) se ejecutaría
    realmente 5 horas antes (de día) según el reloj del servidor."""
    from src.main.service.irrigationServ import start_irrigation
    from src.main.repositories import controlRep as control_repo

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    iniciados = 0

    horarios = (
        db.query(horarios_riego).filter(horarios_riego.activo == True).all()  # noqa: E712
    )
    for horario in horarios:
        try:
            if horario.siempre_activo:
                continue  # sin franja fija: lo maneja check_ml_cooldown_and_irrigate

            asig = db.query(asignaciones_iot).filter(
                asignaciones_iot.id == horario.id_asignacion
            ).first()
            if not asig or not asig.activo:
                continue

            tz = _get_timezone(asig.usuario.zona_horaria if asig.usuario else None)
            now_local = datetime.now(tz).replace(tzinfo=None)
            dia_actual_local = now_local.weekday()  # 0=lunes ... 6=domingo

            dias = horario.dias_semana or []
            if dias and dia_actual_local not in dias:
                continue

            hi = horario.hora_inicio
            coincide_hora = now_local.hour == hi.hour and now_local.minute == hi.minute
            if not coincide_hora:
                continue

            if (
                horario.ultima_ejecucion
                and horario.ultima_ejecucion.date() == now_utc.date()
                and horario.ultima_ejecucion.hour == now_utc.hour
                and horario.ultima_ejecucion.minute == now_utc.minute
            ):
                continue  # ya ejecutado en este minuto (protege contra doble disparo)

            sesion_activa = control_repo.queryObtenerDatosControlSesionActiva(db, asig.id)
            tank_config = control_repo.queryObtenerDatosControlConfigT(db, asig)
            if sesion_activa or (tank_config and tank_config.bomba_encendida):
                continue

            start_irrigation(
                db=db,
                assignment=asig,
                irrigation_type="programado",
                requested_seconds=horario.duracion_segundos,
                now=now_utc,
            )
            horario.ultima_ejecucion = now_utc
            session_repository.add(db, horario)
            session_repository.commit(db)
            iniciados += 1
            logger.info(
                f"[HORARIOS] Riego programado iniciado para asignación {horario.id_asignacion} (horario {horario.id}), hora local {now_local.strftime('%H:%M')} ({tz})."
            )
        except Exception:
            session_repository.rollback(db)
            logger.exception(f"Error ejecutando horario fijo {horario.id}")

    return iniciados
