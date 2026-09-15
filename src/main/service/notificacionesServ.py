from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.main.repositories import notificacionesRep as data_repository
from src.main.repositories import sessionRep as session_repository
from src.main.service.notifications.websocketManagerServ import broadcast_ws_event

CRITICAL_SEVERITIES = {"critico", "critica", "emergencia"}


def _to_response(alert, tipo) -> dict:
    is_recovered = alert.estado == "resuelta"
    titulo = (
        f"Alerta recuperada: {tipo.nombre}"
        if is_recovered
        else f"Alerta: {tipo.nombre}"
    )
    severidad = (
        "info"
        if is_recovered
        else (
            "critica"
            if (tipo.severidad or "").lower() in CRITICAL_SEVERITIES
            else "advertencia"
        )
    )
    timestamp = alert.ultima_notificacion_en or alert.fecha
    return {
        "id": str(alert.id),
        "titulo": titulo,
        "mensaje": alert.mensaje,
        "severidad": severidad,
        "timestamp": int(timestamp.timestamp() * 1000) if timestamp else 0,
        "leida": bool(alert.notificacion_leida),
        "link": "/dashboard/agricultor/notificaciones",
        "origen": tipo.nombre,
    }


def listar_notificacionesServ(db: Session, current_user) -> list[dict]:
    rows = data_repository.queryListNotificaciones(db, current_user.id_usuario)
    return [_to_response(alert, tipo) for alert, tipo in rows]


def marcar_leidaServ(db: Session, current_user, id_alerta: int) -> dict:
    alert = data_repository.queryAlertaUsuario(db, current_user.id_usuario, id_alerta)
    if not alert:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    alert.notificacion_leida = True
    session_repository.commit(db)
    broadcast_ws_event({"tipo": "notificaciones_sync"}, current_user.id_usuario)
    return {"success": True}


def marcar_todas_leidasServ(db: Session, current_user) -> dict:
    data_repository.queryAlertasUsuarioQuery(db, current_user.id_usuario).update(
        {"notificacion_leida": True}, synchronize_session=False
    )
    session_repository.commit(db)
    broadcast_ws_event({"tipo": "notificaciones_sync"}, current_user.id_usuario)
    return {"success": True}


def limpiar_notificacionesServ(db: Session, current_user) -> dict:
    data_repository.queryAlertasUsuarioQuery(db, current_user.id_usuario).update(
        {"notificacion_eliminada": True}, synchronize_session=False
    )
    session_repository.commit(db)
    broadcast_ws_event({"tipo": "notificaciones_sync"}, current_user.id_usuario)
    return {"success": True}
