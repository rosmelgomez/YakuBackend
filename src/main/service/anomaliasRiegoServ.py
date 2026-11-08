"""Detección de anomalías físicas durante el riego a partir de la telemetría
del actuador (HU-19 y HU-21).

- Obstrucción / falta de suministro (CP32): válvula abierta, ciclo en curso y
  el caudalímetro sin pulsos pasados RIEGO_SIN_FLUJO_SEG segundos. Se detiene
  el riego, se bloquea el actuador (queda desactivado hasta que el agricultor
  lo vuelva a activar tras revisar) y se avisa con alerta crítica.
- Posible fuga (CP33): caudal mayor a CAUDAL_FUGA_L_MIN durante el ciclo. Se
  avisa una vez por ciclo; el riego sigue.
- Falla de hardware (CP35): el equipo envía `error_hardware` en su reporte. Se
  cierra el riego, el actuador queda "inoperable" (desactivado) y se avisa a
  los administradores.

Todo es best-effort: un error aquí nunca debe impedir guardar la telemetría.
"""

import logging
import os
import time

from sqlalchemy.orm import Session

from src.main.core.timeUtils import utc_now_naive
from src.main.model.models import asignaciones_iot, logs_sistema
from src.main.repositories import irrigationRep as irrigation_repository
from src.main.repositories import sessionRep as session_repository

logger = logging.getLogger(__name__)

RIEGO_SIN_FLUJO_SEG = int(os.getenv("RIEGO_SIN_FLUJO_SEG", "10"))
CAUDAL_FUGA_L_MIN = float(os.getenv("CAUDAL_FUGA_L_MIN", "15"))
_FALLA_HW_REPETIR_SEG = 600

MENSAJE_OBSTRUCCION = (
    "Alerta: Posible obstrucción o falta de suministro de agua. Riego detenido."
)
MENSAJE_FUGA = "Anomalía de flujo: Posible fuga en el conducto de la parcela"
MENSAJE_FALLA_HW = (
    "Falla de hardware detectada en el actuador. Requiere revisión técnica"
)

# Avisos ya enviados (en memoria) para no repetirlos en cada reporte de 1 s.
_fuga_avisada: set[int] = set()
_falla_hw_avisada: dict[int, float] = {}


def _es_flujometro(data) -> bool:
    return data.metodo_medicion == "flujometro" or data.litros_riego is not None


def _bloquear_actuador(db: Session, asig: asignaciones_iot, accion: str, detalle: str) -> None:
    """Deja el actuador en estado de falla SOLO en la BD y le ordena cerrar.

    No se envía `funcionamiento_activo=false` al equipo: con eso el firmware de
    flujo deja de mandar su heartbeat y el nodo aparecería "Fuera de línea" (y
    dispararía la alerta de red) aunque esté conectado. La asignación inactiva
    basta: el riego automático (schedulerServ) y el manual
    (find_pump_assignment) solo usan actuadores activos. Los sensores son
    otros dispositivos y no se tocan: siguen enviando telemetría.
    El agricultor lo vuelve a activar desde Control de Riego tras revisar."""
    from src.main.service.irrigationServ import _publish_relay_command, build_relay_command

    if asig.activo:
        asig.activo = False
        session_repository.add(db, asig)
    session_repository.add(
        db,
        logs_sistema(
            id_usuario=asig.id_usuario,
            accion=accion,
            modulo="hardware",
            descripcion=detalle,
            fecha=utc_now_naive(),
        ),
    )
    session_repository.commit(db)
    try:
        _publish_relay_command(asig, build_relay_command("OFF"))
    except Exception as exc:
        logger.warning(f"No se pudo enviar OFF al actuador bloqueado: {exc}")


def _detener_por_obstruccion(db: Session, asig: asignaciones_iot, data) -> None:
    from src.main.service.irrigationServ import stop_irrigation
    from src.main.service.notifications.alertEngineServ import notificar_problema_riego

    nombre = asig.dispositivo.nombre if asig.dispositivo else f"asignación {asig.id}"
    logger.warning(
        "[ANOMALIA] Sin flujo en %s tras %ss con la válvula abierta: se detiene el riego.",
        nombre,
        data.tiempo_ejecutado_seg,
    )
    # El OFF lo manda _bloquear_actuador (una sola orden al relé).
    stop_irrigation(db, asig, "sin_flujo", publish=False)
    _bloquear_actuador(
        db,
        asig,
        "Riego detenido por falta de flujo",
        f"El actuador {nombre} abrió la válvula pero el caudalímetro no registró pulsos "
        f"en {data.tiempo_ejecutado_seg}s. Quedó desactivado hasta revisar el suministro.",
    )
    notificar_problema_riego(
        db,
        asig.id_usuario,
        "Posible obstrucción en el riego",
        f"{MENSAJE_OBSTRUCCION} El actuador {nombre} quedó en estado de falla hasta "
        "revisar el suministro de agua; vuelve a activarlo en Control de Riego.",
        severidad="critica",
    )


def _avisar_fuga(db: Session, asig: asignaciones_iot, data, id_riego: int) -> None:
    from src.main.service.notifications.alertEngineServ import notificar_problema_riego

    _fuga_avisada.add(id_riego)
    caudal = float(data.caudal_l_min or 0)
    logger.warning(
        "[ANOMALIA] Caudal %.2f L/min supera el límite %.2f L/min (riego %s).",
        caudal,
        CAUDAL_FUGA_L_MIN,
        id_riego,
    )
    notificar_problema_riego(
        db,
        asig.id_usuario,
        "Anomalía de flujo",
        f"{MENSAJE_FUGA}. Caudal detectado: {caudal:.1f} L/min "
        f"(límite calibrado: {CAUDAL_FUGA_L_MIN:.1f} L/min).",
        severidad="advertencia",
    )


def _registrar_falla_hardware(db: Session, asig: asignaciones_iot, data) -> None:
    from src.main.service.irrigationServ import stop_irrigation
    from src.main.service.notifications.alertEngineServ import (
        notificar_administradores,
        notificar_problema_riego,
    )

    device_id = asig.id_dispositivo
    ahora = time.monotonic()
    ultimo = _falla_hw_avisada.get(device_id)
    if ultimo is not None and ahora - ultimo < _FALLA_HW_REPETIR_SEG:
        return
    _falla_hw_avisada[device_id] = ahora

    nombre = asig.dispositivo.nombre if asig.dispositivo else f"dispositivo {device_id}"
    detalle = data.error_hardware
    logger.error("[ANOMALIA] Falla de hardware en %s: %s", nombre, detalle)

    try:
        stop_irrigation(db, asig, "falla_hardware", publish=False)
    except Exception:
        session_repository.rollback(db)
        logger.exception("No se pudo cerrar el riego tras la falla de hardware")

    _bloquear_actuador(
        db,
        asig,
        "Falla de hardware",
        f"El actuador {nombre} reportó una falla eléctrica ({detalle}) al accionar el "
        "relé/válvula. Quedó inoperable hasta su revisión.",
    )
    notificar_administradores(
        db,
        "FALLA_HARDWARE",
        MENSAJE_FALLA_HW,
        f"{MENSAJE_FALLA_HW}. Nodo: {nombre}. Detalle reportado: {detalle}. "
        "El nodo quedó marcado como inoperable.",
        severidad="critica",
        id_asignacion=asig.id,
        evento_id=f"falla-hw-{device_id}-{int(time.time())}",
    )
    notificar_problema_riego(
        db,
        asig.id_usuario,
        "Falla de hardware en el actuador",
        f"El actuador {nombre} reportó una falla eléctrica y fue desactivado por "
        "seguridad. El administrador fue notificado.",
        severidad="critica",
    )


def evaluar_anomalias_actuador(db: Session, asig: asignaciones_iot | None, data) -> None:
    if asig is None:
        return
    try:
        if data.error_hardware:
            _registrar_falla_hardware(db, asig, data)
            return

        if data.estado_bomba != "ON" or not _es_flujometro(data):
            return

        from src.main.service.irrigationServ import is_paused_session

        sesion = irrigation_repository.queryStopIrrigationSession(db, asig)
        if sesion is None or is_paused_session(sesion):
            return

        sin_pulsos = (data.litros_riego or 0) <= 0 and (data.pulsos_riego or 0) == 0
        if (
            sin_pulsos
            and data.tiempo_ejecutado_seg is not None
            and data.tiempo_ejecutado_seg >= RIEGO_SIN_FLUJO_SEG
        ):
            _detener_por_obstruccion(db, asig, data)
            return

        if (
            data.caudal_l_min is not None
            and data.caudal_l_min > CAUDAL_FUGA_L_MIN
            and sesion.id not in _fuga_avisada
        ):
            _avisar_fuga(db, asig, data, sesion.id)
    except Exception:
        session_repository.rollback(db)
        logger.exception("Error evaluando anomalías del actuador")
