"""Ciclo de vida del cultivo: fecha de cosecha, finalización y recordatorio.

Finalizar un cultivo NO borra nada: riegos, lecturas, predicciones y auditoría
siguen ligados al cultivo (las filas de asignación conservan id_cultivo). Lo
que cambia es que:
  * se cierra el riego en curso (válvula/bomba en OFF),
  * sus dispositivos vuelven al stock disponible (el administrador puede
    reasignarlos al siguiente cultivo) y la IA/planificador dejan de evaluarlo
    porque sus asignaciones quedan inactivas,
  * la fuente de agua queda libre (ningún cultivo en curso la usa),
  * el cultivo pasa a estado 'finalizado' y solo se consulta su historial.
"""

import logging
from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.main.core.timeUtils import utc_now_naive
from src.main.model.models import asignaciones_iot, cultivos, logs_sistema, riego
from src.main.repositories import sessionRep as session_repository

logger = logging.getLogger(__name__)

ESTADO_FINALIZADO = "finalizado"
CODIGO_COSECHA = "COSECHA_CULTIVO"
LINK_CULTIVOS = "/dashboard/agricultor/cultivos"


def parse_fecha(valor: str | None, campo: str) -> date | None:
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato de {campo} inválido. Utilice AAAA-MM-DD.",
        )


def validar_fecha_cosecha(fecha_cosecha: date | None, fecha_siembra: date | None) -> None:
    if fecha_cosecha and fecha_siembra and fecha_cosecha <= fecha_siembra:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de cosecha debe ser posterior a la fecha de siembra.",
        )


def _cultivo_propio(db: Session, id_cultivo: int, current_user) -> cultivos:
    cultivo = db.query(cultivos).filter(cultivos.id_cultivo == id_cultivo).first()
    if cultivo is None or (
        current_user.id_rol != 1 and cultivo.id_usuario != current_user.id_usuario
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cultivo no encontrado.")
    return cultivo


def _invalidar_caches(id_usuario: int) -> None:
    try:
        from src.main.core.cache import backend_cache

        for prefijo in ("dashboard_data", "cultivos_base", "historico"):
            backend_cache.invalidate(f"{prefijo}:{id_usuario}")
    except Exception:
        pass


def _log(db: Session, current_user, accion: str, descripcion: str) -> None:
    session_repository.add(
        db,
        logs_sistema(
            id_usuario=current_user.id_usuario,
            accion=accion,
            modulo="Cultivos",
            descripcion=descripcion,
            fecha=utc_now_naive(),
        ),
    )


def actualizar_fecha_cosechaServ(id_cultivo: int, fecha: str | None, db: Session, current_user) -> dict:
    cultivo = _cultivo_propio(db, id_cultivo, current_user)
    if cultivo.estado == ESTADO_FINALIZADO:
        raise HTTPException(status_code=400, detail="El cultivo ya está finalizado.")
    nueva = parse_fecha(fecha, "fecha de cosecha")
    validar_fecha_cosecha(nueva, cultivo.fecha_siembra)
    anterior = cultivo.fecha_cosecha_estimada
    cultivo.fecha_cosecha_estimada = nueva
    # Si se mueve la fecha, el recordatorio vuelve a avisar cuando llegue.
    cultivo.cosecha_notificada = False
    session_repository.add(db, cultivo)
    _log(
        db,
        current_user,
        "Fecha de cosecha",
        f"{cultivo.nombre_planta} (#{cultivo.id_cultivo}): {anterior or 'sin fecha'} -> {nueva or 'sin fecha'}.",
    )
    session_repository.commit(db)
    _invalidar_caches(cultivo.id_usuario)
    return {
        "id_cultivo": cultivo.id_cultivo,
        "fecha_cosecha_estimada": nueva.isoformat() if nueva else None,
    }


def _dispositivos_del_cultivo(db: Session, id_cultivo: int) -> list:
    """Equipos cuyo titular vigente es este cultivo (su asignación más reciente
    apunta a él y siguen asignados). Un equipo que ya pasó a otro cultivo no se toca."""
    from src.main.model.models import dispositivos

    ids = {
        fila.id_dispositivo
        for fila in db.query(asignaciones_iot.id_dispositivo).filter(
            asignaciones_iot.id_cultivo == id_cultivo
        )
    }
    equipos = []
    for dev in db.query(dispositivos).filter(dispositivos.id_dispositivo.in_(ids)).all() if ids else []:
        ultima = max(dev.asignaciones or [], key=lambda a: a.id, default=None)
        if dev.estado == "asignado" and ultima is not None and ultima.id_cultivo == id_cultivo:
            equipos.append(dev)
    return equipos


def finalizar_cultivoServ(id_cultivo: int, db: Session, current_user) -> dict:
    from src.main.service.dispositivoServ import liberar_dispositivo
    from src.main.service.irrigationServ import stop_irrigation

    cultivo = _cultivo_propio(db, id_cultivo, current_user)
    if cultivo.estado == ESTADO_FINALIZADO:
        raise HTTPException(status_code=400, detail="El cultivo ya está finalizado.")

    # 1. Cerrar el riego en curso: apaga la válvula/bomba y lo da por completado.
    abiertos = (
        db.query(riego, asignaciones_iot)
        .join(asignaciones_iot, asignaciones_iot.id == riego.id_asignacion)
        .filter(asignaciones_iot.id_cultivo == id_cultivo, riego.estado == False)  # noqa: E712
        .all()
    )
    riegos_cerrados = 0
    for _, asig in abiertos:
        try:
            if stop_irrigation(db, asig, "cultivo_finalizado") is not None:
                riegos_cerrados += 1
        except Exception:
            logger.exception("No se pudo cerrar el riego al finalizar el cultivo %s", id_cultivo)
            db.rollback()

    # 2. Liberar los dispositivos (vuelven al stock; sus asignaciones quedan inactivas).
    equipos = _dispositivos_del_cultivo(db, id_cultivo)
    nombres = []
    for dev in equipos:
        liberar_dispositivo(db, dev)
        nombres.append(dev.nombre)

    # 3. Cerrar el cultivo. La fuente de agua se conserva como dato histórico,
    #    pero queda libre: ya no hay un cultivo en curso que la use.
    cultivo = _cultivo_propio(db, id_cultivo, current_user)
    cultivo.estado = ESTADO_FINALIZADO
    cultivo.fecha_finalizacion = utc_now_naive()
    session_repository.add(db, cultivo)
    _log(
        db,
        current_user,
        "Cultivo finalizado",
        f"{cultivo.nombre_planta} (#{cultivo.id_cultivo}) finalizado. "
        f"Dispositivos liberados: {', '.join(nombres) or 'ninguno'}. Riegos cerrados: {riegos_cerrados}.",
    )
    session_repository.commit(db)
    _invalidar_caches(cultivo.id_usuario)

    return {
        "id_cultivo": cultivo.id_cultivo,
        "estado": cultivo.estado,
        "fecha_finalizacion": cultivo.fecha_finalizacion.isoformat() + "Z",
        "dispositivos_liberados": nombres,
        "riegos_cerrados": riegos_cerrados,
        "mensaje": f"Cultivo {cultivo.nombre_planta} finalizado. Su historial sigue disponible.",
    }


# ---------------------------------------------------------------------------
# Recordatorio de cosecha (lo llama el planificador)
# ---------------------------------------------------------------------------

_ultima_revision_cosecha: datetime | None = None
_REVISAR_CADA_SEG = 3600


def verificar_cosechas(db: Session, hoy: date | None = None, forzar: bool = False) -> int:
    """Avisa una sola vez al agricultor cuando un cultivo en curso llega a su
    fecha de cosecha estimada. No lo finaliza solo: la cosecha real puede
    adelantarse o atrasarse."""
    global _ultima_revision_cosecha
    ahora = utc_now_naive()
    if (
        not forzar
        and _ultima_revision_cosecha is not None
        and (ahora - _ultima_revision_cosecha).total_seconds() < _REVISAR_CADA_SEG
    ):
        return 0
    _ultima_revision_cosecha = ahora
    hoy = hoy or ahora.date()

    pendientes = (
        db.query(cultivos)
        .filter(
            cultivos.estado == "activo",
            cultivos.fecha_cosecha_estimada.isnot(None),
            cultivos.fecha_cosecha_estimada <= hoy,
            (cultivos.cosecha_notificada.is_(None)) | (cultivos.cosecha_notificada == False),  # noqa: E712
        )
        .all()
    )
    if not pendientes:
        return 0

    from src.main.service.notifications.alertEngineServ import notificar_agricultor

    for cultivo in pendientes:
        fecha = cultivo.fecha_cosecha_estimada.strftime("%d/%m/%Y")
        notificar_agricultor(
            db,
            cultivo.id_usuario,
            CODIGO_COSECHA,
            f"{cultivo.nombre_planta}: fecha de cosecha alcanzada",
            f"Tu cultivo {cultivo.nombre_planta} llegó a su fecha de cosecha estimada ({fecha}). "
            "Cuando termines la cosecha, finalízalo en Mis cultivos para liberar sus dispositivos; "
            "su historial seguirá disponible.",
            link=LINK_CULTIVOS,
        )
        cultivo.cosecha_notificada = True
        session_repository.add(db, cultivo)
    session_repository.commit(db)
    return len(pendientes)


# ---------------------------------------------------------------------------
# Historial de dispositivos usados por el cultivo (consulta, también finalizado)
# ---------------------------------------------------------------------------


def listar_dispositivos_cultivoServ(id_cultivo: int, db: Session, current_user) -> dict:
    """Equipos que trabajaron en el cultivo, con su periodo de uso y los riegos
    que ejecutaron. Funciona igual en cultivos en curso y finalizados."""
    from sqlalchemy import func

    from src.main.model.models import dispositivos
    from src.main.service.deviceHealthServ import _is_actuator_device

    cultivo = _cultivo_propio(db, id_cultivo, current_user)
    filas = (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id_cultivo == id_cultivo)
        .order_by(asignaciones_iot.id.asc())
        .all()
    )
    por_equipo: dict[int, list] = {}
    for a in filas:
        por_equipo.setdefault(a.id_dispositivo, []).append(a)

    finalizado = cultivo.estado == ESTADO_FINALIZADO
    equipos = []
    for id_dev, asigs in por_equipo.items():
        dev = db.get(dispositivos, id_dev)
        if dev is None:
            continue
        ids = [a.id for a in asigs]
        riegos_n, litros = (
            db.query(func.count(riego.id), func.coalesce(func.sum(riego.cantidad_agua_litros), 0))
            .filter(riego.id_asignacion.in_(ids))
            .one()
        )
        vigentes = dev.asignaciones_vigentes
        en_uso = (
            not finalizado
            and dev.estado == "asignado"
            and bool(vigentes)
            and vigentes[0].id_cultivo == id_cultivo
        )
        desde = min((a.fecha_registro for a in asigs if a.fecha_registro), default=None)
        hasta = None if en_uso else (cultivo.fecha_finalizacion if finalizado else None)
        equipos.append(
            {
                "id_dispositivo": dev.id_dispositivo,
                "nombre": dev.nombre,
                "tipo": dev.tipo.nombre if dev.tipo else None,
                "rol": "actuador" if _is_actuator_device(dev) else "sensor",
                "client_id_mqtt": dev.client_id_mqtt,
                "mac_address": dev.mac_address,
                "firmware_version": dev.firmware_version,
                "desde": desde.isoformat() + "Z" if desde else None,
                "hasta": hasta.isoformat() + "Z" if hasta else None,
                "en_uso": en_uso,
                "riegos": int(riegos_n or 0),
                "litros": round(float(litros or 0), 2),
            }
        )
    return {
        "id_cultivo": cultivo.id_cultivo,
        "estado": cultivo.estado,
        "dispositivos": equipos,
    }
