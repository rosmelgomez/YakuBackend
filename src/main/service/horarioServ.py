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

SEGUNDOS_POR_DIA = 24 * 3600


def _calcular_duracion_segundos(hora_inicio: time, hora_fin: time) -> int:
    """Calcula el ancho en segundos de la ventana horaria "de hora a hora"
    que ingresa el usuario. Esta ventana YA NO es un evento de riego unico e
    ininterrumpido (por eso no tiene tope de 60 min: puede cubrir varias
    horas, ej. 06:00-23:00) -- es el rango durante el cual el riego
    automatico por ML puede ejecutarse; dentro de la ventana sigue rigiendo
    el tiempo de riego por ciclo y el cooldown configurados aparte.

    Soporta rangos que cruzan la medianoche: si hora_fin es menor o igual a
    hora_inicio, se asume que termina al dia siguiente (ej. 23:50 -> 00:10
    dura 20 minutos). Caso especial: si ambas horas son iguales (ej.
    06:00 -> 06:00), se interpreta como "todo el dia" (24 horas) en vez de
    rechazarse -- es la lectura mas intuitiva para quien configura el mismo
    valor en ambos campos."""
    inicio_seg = hora_inicio.hour * 3600 + hora_inicio.minute * 60 + hora_inicio.second
    fin_seg = hora_fin.hour * 3600 + hora_fin.minute * 60 + hora_fin.second

    if fin_seg == inicio_seg:
        return SEGUNDOS_POR_DIA

    duracion = fin_seg - inicio_seg
    if duracion < 0:
        duracion += SEGUNDOS_POR_DIA  # el rango cruza la medianoche
    return duracion


def _hora_en_ventana(hora_actual_seg: int, inicio_seg: int, fin_seg: int) -> bool:
    """True si `hora_actual_seg` (segundos desde medianoche, hora local) cae
    dentro de [inicio_seg, fin_seg), soportando ventanas que cruzan la
    medianoche (inicio > fin) y la ventana de 24h completas (inicio == fin,
    ver _calcular_duracion_segundos)."""
    if inicio_seg == fin_seg:
        return True  # ventana de 24 horas: siempre dentro
    if inicio_seg < fin_seg:
        return inicio_seg <= hora_actual_seg < fin_seg
    return hora_actual_seg >= inicio_seg or hora_actual_seg < fin_seg


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
    habilitar el riego automático por IA."""
    return (
        db.query(horarios_riego)
        .filter(horarios_riego.id_asignacion == id_asignacion)
        .first()
        is not None
    )


def horario_permite_ahora(
    db: Session, id_asignacion: int, now_utc: datetime | None = None
) -> bool:
    """Indica si, en este momento, algun horario ACTIVO de esta asignación
    permite que el riego automatico por IA se ejecute. Un horario "siempre
    activo" siempre permite; un horario con franja horaria (hora_inicio a
    hora_fin, dias_semana) solo permite si la hora y el dia local actuales
    caen dentro de esa ventana. Esta funcion NO decide si regar -- solo si
    es un momento permitido para que check_ml_cooldown_and_irrigate evalue.
    """
    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)

    horarios = (
        db.query(horarios_riego)
        .filter(
            horarios_riego.id_asignacion == id_asignacion,
            horarios_riego.activo == True,  # noqa: E712
        )
        .all()
    )
    if not horarios:
        return False

    for horario in horarios:
        if horario.siempre_activo:
            return True

        asig = (
            db.query(asignaciones_iot)
            .filter(asignaciones_iot.id == id_asignacion)
            .first()
        )
        tz = _get_timezone(asig.usuario.zona_horaria if asig and asig.usuario else None)
        now_local = now_utc.replace(tzinfo=timezone.utc).astimezone(tz).replace(tzinfo=None)
        dia_actual_local = now_local.weekday()

        dias = horario.dias_semana or []
        if dias and dia_actual_local not in dias:
            continue

        hi, hf = horario.hora_inicio, horario.hora_fin
        if hi is None or hf is None:
            continue
        inicio_seg = hi.hour * 3600 + hi.minute * 60 + hi.second
        fin_seg = hf.hour * 3600 + hf.minute * 60 + hf.second
        actual_seg = (
            now_local.hour * 3600 + now_local.minute * 60 + now_local.second
        )
        if _hora_en_ventana(actual_seg, inicio_seg, fin_seg):
            return True

    return False


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
    """DEPRECADO: los horarios con franja fija ya no disparan un riego
    manual de duracion=ancho-de-ventana al llegar `hora_inicio`. Ahora son
    puramente una ventana de PERMISO para el riego automatico por IA (ver
    `horario_permite_ahora`, usado por
    `schedulerServ.check_ml_cooldown_and_irrigate`): la IA solo evalua y
    puede regar cuando la hora/dia local actual cae dentro de la ventana
    configurada, respetando siempre el tiempo de riego por ciclo y el
    cooldown ya definidos aparte. Esta funcion se mantiene solo para no
    romper la firma que invoca el scheduler; no hace nada."""
    return 0
