"""Monitoreo de red de los nodos IoT y auditoría de eventos de riego.

- Monitoreo de Red (HU-10, CP16/CP17): estado "en_linea"/"fuera_de_linea" de
  cada nodo calculado al vuelo con su ultimo_ping. No escribe nada: cuando el
  nodo vuelve a publicar, el siguiente refresco ya lo muestra en línea.
- Alerta de red (HU-22, CP36): aviso a los administradores cuando un nodo
  asignado lleva más de RED_ALERTA_MINUTOS sin reportar. Se resuelve sola al
  volver la conexión, así un nuevo corte vuelve a avisar.
- Auditoría de eventos (HU-14, CP24/CP25): cruza la decisión de riego con el
  volumen medido para validar cada evento.
"""

import logging
import os
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from src.main.core.timeUtils import utc_now_naive
from src.main.model.models import (
    alertas,
    asignaciones_iot,
    dispositivos,
    predicciones_ml,
    riego,
)
from src.main.repositories import sessionRep as session_repository
from src.main.service.deviceHealthServ import (
    DEVICE_OFFLINE_TIMEOUT_SECONDS,
    _is_actuator_device,
    _tipo_nombre,
)

logger = logging.getLogger(__name__)

ID_ROL_ADMINISTRADOR = 1
CODIGO_RED_NODO_DESCONECTADO = "RED_NODO_DESCONECTADO"
RED_ALERTA_MINUTOS = int(os.getenv("RED_ALERTA_MINUTOS", "10"))
_RED_CHECK_CADA_SEG = 60
_ultima_revision_red: datetime | None = None


def _solo_admin(current_user) -> None:
    if getattr(current_user, "id_rol", None) != ID_ROL_ADMINISTRADOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. No tiene permisos de administrador.",
        )


def umbral_offline_seg(device: dispositivos) -> int:
    """Segundos sin ping tras los que el nodo se considera fuera de línea.

    Los sensores publican cada intervalo_captura_segundos; se toleran dos
    intervalos perdidos para no marcar offline un nodo que reporta lento."""
    base = DEVICE_OFFLINE_TIMEOUT_SECONDS
    if _is_actuator_device(device):
        return base
    intervalo = int(getattr(device, "intervalo_captura_segundos", None) or 60)
    return max(base, intervalo * 2 + 30)


def estado_conexion(device: dispositivos, now: datetime) -> str:
    if device.ultimo_ping is None:
        return "sin_datos"
    segundos = (now - device.ultimo_ping).total_seconds()
    return "en_linea" if segundos <= umbral_offline_seg(device) else "fuera_de_linea"


def _asignacion_vigente(device: dispositivos) -> asignaciones_iot | None:
    asignaciones = sorted(device.asignaciones or [], key=lambda a: a.id, reverse=True)
    for asig in asignaciones:
        if asig.activo:
            return asig
    return asignaciones[0] if asignaciones else None


def _dispositivos_en_campo(db: Session) -> list[dispositivos]:
    return (
        db.query(dispositivos)
        .options(
            joinedload(dispositivos.asignaciones).joinedload(asignaciones_iot.usuario),
            joinedload(dispositivos.asignaciones).joinedload(asignaciones_iot.cultivo),
        )
        .filter(
            (dispositivos.estado == "asignado") | (dispositivos.ultimo_ping.isnot(None))
        )
        .order_by(dispositivos.nombre)
        .all()
    )


def listar_monitoreo_redServ(db: Session, current_user) -> dict:
    _solo_admin(current_user)
    now = utc_now_naive()
    nodos = []
    for device in _dispositivos_en_campo(db):
        asig = _asignacion_vigente(device)
        usuario = asig.usuario if asig else None
        cultivo = asig.cultivo if asig else None
        segundos = (
            int((now - device.ultimo_ping).total_seconds())
            if device.ultimo_ping
            else None
        )
        nodos.append(
            {
                "id": device.id_dispositivo,
                "nombre": device.nombre,
                "tipo": device.tipo.nombre if device.tipo else None,
                "rol": "actuador" if _is_actuator_device(device) else "sensor",
                "client_id_mqtt": device.client_id_mqtt,
                "mac_address": device.mac_address,
                "firmware_version": device.firmware_version,
                "ultimo_ping": device.ultimo_ping.isoformat() + "Z"
                if device.ultimo_ping
                else None,
                "segundos_sin_ping": segundos,
                "umbral_offline_seg": umbral_offline_seg(device),
                "estado_conexion": estado_conexion(device, now),
                "usuario": " ".join(
                    p for p in (getattr(usuario, "nombre", None), getattr(usuario, "apellido", None)) if p
                )
                or None,
                "cultivo": getattr(cultivo, "nombre_planta", None),
            }
        )
    return {
        "generado_en": now.isoformat() + "Z",
        "red_alerta_minutos": RED_ALERTA_MINUTOS,
        "nodos": nodos,
    }


# ---------------------------------------------------------------------------
# Alerta de red al administrador (CP36)
# ---------------------------------------------------------------------------


def verificar_alertas_red(db: Session, now: datetime | None = None, forzar: bool = False) -> int:
    """Crea la alerta "Nodo desconectado" para los administradores y la
    resuelve al volver el nodo. Se ejecuta desde el planificador cada 10 s,
    pero solo trabaja una vez por minuto."""
    global _ultima_revision_red
    now = now or utc_now_naive()
    if (
        not forzar
        and _ultima_revision_red is not None
        and (now - _ultima_revision_red).total_seconds() < _RED_CHECK_CADA_SEG
    ):
        return 0
    _ultima_revision_red = now

    from src.main.repositories import alertEngineRep
    from src.main.service.notifications.alertEngineServ import notificar_administradores

    tipo = alertEngineRep.queryTipoAlertaPorCodigo(db, CODIGO_RED_NODO_DESCONECTADO)
    if tipo is None:
        return 0

    creadas = 0
    for device in _dispositivos_en_campo(db):
        if device.ultimo_ping is None or device.estado != "asignado":
            continue
        asig = _asignacion_vigente(device)
        if asig is None:
            continue
        ids_asig = [a.id for a in device.asignaciones]
        activas = (
            db.query(alertas)
            .filter(
                alertas.id_tipo_alerta == tipo.id,
                alertas.id_asignacion.in_(ids_asig),
                alertas.estado == "activa",
            )
            .all()
        )
        segundos = (now - device.ultimo_ping).total_seconds()
        limite = max(RED_ALERTA_MINUTOS * 60, umbral_offline_seg(device))

        if segundos > limite and not activas:
            minutos = int(segundos // 60)
            notificar_administradores(
                db,
                CODIGO_RED_NODO_DESCONECTADO,
                "Alerta de Red: Nodo desconectado. Telemetría interrumpida",
                f"Alerta de Red: Nodo desconectado. Telemetría interrumpida. "
                f"El nodo {device.nombre} ({device.client_id_mqtt or 'sin client id'}) "
                f"no reporta por MQTT hace {minutos} min.",
                severidad="critica",
                link="/dashboard/administrador/monitoreo-red",
                id_asignacion=asig.id,
                evento_id=f"red-{device.id_dispositivo}-{int(now.timestamp())}",
            )
            creadas += 1
        elif activas and segundos <= umbral_offline_seg(device):
            for alerta in activas:
                alerta.estado = "resuelta"
                alerta.resuelta_en = now
                alerta.comentario = "El nodo volvió a reportar por MQTT."
                session_repository.add(db, alerta)
            session_repository.commit(db)
    return creadas


# ---------------------------------------------------------------------------
# Auditoría de eventos de riego (CP24/CP25)
# ---------------------------------------------------------------------------

ESTADO_VALIDADO = "Validado Volumétricamente"
ESTADO_A_CIEGAS = "Alerta: Ejecución a Ciegas - Revisar Hardware"


def _diagnostico(evento: riego) -> tuple[str, str]:
    if not evento.estado:
        return "En curso", "en_curso"
    litros = float(evento.cantidad_agua_litros or 0)
    if litros > 0:
        return ESTADO_VALIDADO, "validado"
    return ESTADO_A_CIEGAS, "a_ciegas"


def _decision(evento: riego, pred: predicciones_ml | None) -> str:
    tipo = (evento.tipo_riego or "").lower()
    if pred is not None and pred.recomendacion:
        return "Regar" if pred.recomendacion == "regar" else "No regar"
    if "ml" in tipo or "auto" in tipo:
        return "Regar"
    if "horario" in tipo or "program" in tipo:
        return "Riego programado"
    return "Riego manual"


def listar_auditoria_eventosServ(
    db: Session, current_user, id_cultivo: int | None = None, limit: int = 100
) -> list[dict]:
    limit = max(1, min(int(limit or 100), 500))
    query = (
        db.query(riego, asignaciones_iot)
        .join(asignaciones_iot, asignaciones_iot.id == riego.id_asignacion)
        .options(
            joinedload(asignaciones_iot.cultivo),
            joinedload(asignaciones_iot.dispositivo),
            joinedload(asignaciones_iot.usuario),
        )
    )
    if getattr(current_user, "id_rol", None) != ID_ROL_ADMINISTRADOR:
        query = query.filter(riego.id_usuario == current_user.id_usuario)
    if id_cultivo:
        query = query.filter(asignaciones_iot.id_cultivo == id_cultivo)
    filas = query.order_by(riego.id.desc()).limit(limit).all()

    ids_pred = [r.id_prediccion for r, _ in filas if r.id_prediccion]
    preds = {}
    if ids_pred:
        preds = {
            p.id_prediccion: p
            for p in db.query(predicciones_ml).filter(predicciones_ml.id_prediccion.in_(ids_pred))
        }

    eventos = []
    for evento, asig in filas:
        pred = preds.get(evento.id_prediccion)
        diagnostico, codigo = _diagnostico(evento)
        fecha = evento.fecha_inicio or evento.fecha
        eventos.append(
            {
                "id": evento.id,
                "fecha": fecha.isoformat() + "Z" if fecha else None,
                "fecha_fin": evento.fecha_fin.isoformat() + "Z" if evento.fecha_fin else None,
                "cultivo": asig.cultivo.nombre_planta if asig.cultivo else None,
                "usuario": " ".join(
                    p for p in (getattr(asig.usuario, "nombre", None), getattr(asig.usuario, "apellido", None)) if p
                )
                or None,
                "dispositivo": asig.dispositivo.nombre if asig.dispositivo else None,
                "tipo_riego": evento.tipo_riego,
                "decision_ia": _decision(evento, pred),
                "probabilidad": float(pred.probabilidad) if pred and pred.probabilidad is not None else None,
                "litros": round(float(evento.cantidad_agua_litros or 0), 2),
                "duracion_segundos": int(evento.segundos_acumulados or evento.duracion_segundos or 0),
                "motivo_cierre": evento.motivo_cierre,
                "diagnostico": diagnostico,
                "codigo_diagnostico": codigo,
            }
        )
    return eventos
