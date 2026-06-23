import asyncio
import datetime as dt
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from src.db.models import (
    alertas,
    asignaciones_iot,
    configuracion_notificaciones,
    notificaciones,
    suscripciones_push,
    tipos_alerta,
    tipos_metrica,
    umbrales_config,
    usuarios,
)
from src.services.notifications.email import enviar_correo_alerta
from src.services.notifications.webpush import enviar_webpush
from src.services.notifications.websocket_manager import manager


ACTIVE_STATES = ("pendiente", "activa")
METRIC_INFO = {
    "HUM_SUELO": ("Humedad de suelo", "%", 1, 2),
    "TEMP_SUELO": ("Temperatura de suelo", "°C", 3, 4),
    "TEMP_AMB": ("Temperatura ambiente", "°C", 5, 6),
    "HUM_AMB": ("Humedad ambiente", "%", 7, 8),
    "NIVEL_AGUA": ("Nivel del tanque", "%", 9, 10),
}


def default_reminder_minutes(severity: str | None) -> int:
    return 15 if (severity or "").lower() in {"critico", "critica", "emergencia"} else 30


def clamp_reminder_minutes(value: int | None, severity: str | None) -> int:
    if value is None:
        return default_reminder_minutes(severity)
    return max(5, min(1440, int(value)))


def notification_is_due(last_sent: dt.datetime | None, now: dt.datetime, minutes: int) -> bool:
    return last_sent is None or now >= last_sent + dt.timedelta(minutes=minutes)


def _schedule_broadcast(payload: dict, user_id: int) -> None:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.broadcast(payload, user_id=user_id))
        else:
            asyncio.run(manager.broadcast(payload, user_id=user_id))
    except Exception as exc:
        logger.info(f"[WS] Error al transmitir alerta WebSocket: {exc}")


def _last_attempt(db: Session, alert_id: int, channel: str) -> dt.datetime | None:
    row = (
        db.query(notificaciones)
        .filter(
            notificaciones.id_alerta == alert_id,
            notificaciones.canal == channel,
        )
        .order_by(notificaciones.id.desc())
        .first()
    )
    if not row:
        return None
    return row.intentado_en


def _record_notification(
    db: Session,
    alert,
    channel: str,
    subject: str,
    message: str,
    event_type: str,
    success: bool,
    error: str | None = None,
) -> None:
    previous_attempts = db.query(notificaciones).filter(
        notificaciones.id_alerta == alert.id,
        notificaciones.canal == channel,
        notificaciones.tipo_evento == event_type,
    ).count()
    db.add(notificaciones(
        id_alerta=alert.id,
        id_usuario=alert.id_usuario,
        canal=channel,
        asunto=subject,
        mensaje=message,
        enviado=success,
        enviado_en=dt.datetime.now() if success else None,
        error=error,
        tipo_evento=event_type,
        intento=previous_attempts + 1,
        intentado_en=dt.datetime.now(),
    ))


def _deliver(
    db: Session,
    alert,
    alert_type,
    message: str,
    event_type: str,
    preference,
    now: dt.datetime,
) -> None:
    dashboard_enabled = preference.canal_dashboard if preference else True
    email_enabled = preference.canal_email if preference else True
    preference_enabled = preference.activo if preference else True
    if not preference_enabled:
        return

    reminder_minutes = clamp_reminder_minutes(
        preference.recordatorio_minutos if preference else None,
        alert_type.severidad,
    )
    is_reminder = event_type == "recordatorio"
    delivered = False
    subject = (
        f"Alerta recuperada: {alert_type.nombre}"
        if event_type == "recuperacion"
        else f"Alerta: {alert_type.nombre}"
    )

    dashboard_due = not is_reminder or notification_is_due(
        _last_attempt(db, alert.id, "dashboard"), now, reminder_minutes
    )
    if dashboard_enabled and dashboard_due:
        delivered = True
        _record_notification(db, alert, "dashboard", subject, message, event_type, True)
        payload = {
            "id": str(alert.id),
            "titulo": subject,
            "mensaje": message,
            "severidad": "info" if event_type == "recuperacion" else (
                "critica" if alert_type.severidad in {"critico", "critica", "emergencia"} else "advertencia"
            ),
            "valor": float(alert.ultimo_valor_detectado or alert.valor_detectado or 0),
            "tipo_evento": event_type,
        }
        _schedule_broadcast(payload, alert.id_usuario)

        for subscription in db.query(suscripciones_push).filter(
            suscripciones_push.id_usuario == alert.id_usuario
        ).all():
            result = enviar_webpush({
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.key_p256dh, "auth": subscription.key_auth},
            }, subject, message)
            if result == "EXPIRED":
                db.delete(subscription)
            else:
                _record_notification(
                    db, alert, "webpush", subject, message, event_type, result is True,
                    None if result is True else "El proveedor Web Push rechazó el envío",
                )

    # El correo se repite con menor frecuencia para evitar saturar la bandeja.
    email_minutes = max(60, reminder_minutes)
    email_due = not is_reminder or notification_is_due(
        _last_attempt(db, alert.id, "email"), now, email_minutes
    )
    if email_enabled and email_due:
        user = db.query(usuarios).filter(usuarios.id_usuario == alert.id_usuario).first()
        if user and user.correo:
            delivered = True
            body = (
                f"Hola {user.nombre},\n\n{message}\n\n"
                "Ingresa al panel de Yaku para revisar el estado del cultivo.\n\nEquipo Yaku"
            )
            success = enviar_correo_alerta(user.correo, f"YAKU: {subject}", body)
            _record_notification(
                db, alert, "email", f"YAKU: {subject}", body, event_type, success,
                None if success else "Error en el servidor de correo o destinatario rechazado",
            )

    if delivered:
        alert.ultima_notificacion_en = now
        alert.proxima_notificacion_en = now + dt.timedelta(minutes=reminder_minutes)
        alert.cantidad_notificaciones = int(alert.cantidad_notificaciones or 0) + 1
    db.commit()


def _resolve_alerts(db: Session, active_alerts: list, metric_name: str, unit: str, value: float, now: dt.datetime) -> None:
    for alert in active_alerts:
        alert_type = db.query(tipos_alerta).filter(tipos_alerta.id == alert.id_tipo_alerta).first()
        if not alert_type:
            continue
        alert.estado = "resuelta"
        alert.resuelta_en = now
        alert.ultimo_valor_detectado = value
        alert.mensaje = f"{metric_name} volvió al rango normal: {value:.2f}{unit}."
        preference = db.query(configuracion_notificaciones).filter(
            configuracion_notificaciones.id_usuario == alert.id_usuario,
            configuracion_notificaciones.id_tipo_alerta == alert.id_tipo_alerta,
        ).first()
        _deliver(db, alert, alert_type, alert.mensaje, "recuperacion", preference, now)


def evaluar_y_disparar_alerta(
    db: Session,
    id_asignacion: int,
    codigo_metrica: str,
    valor_actual: float,
    *,
    now: dt.datetime | None = None,
) -> None:
    """Crea, recuerda o resuelve una alerta sin duplicarla por cada lectura MQTT."""
    now = now or dt.datetime.now()
    metric = METRIC_INFO.get(codigo_metrica)
    if not metric:
        return
    metric_name, unit, low_type_id, high_type_id = metric

    assignment = db.query(asignaciones_iot).filter(asignaciones_iot.id == id_asignacion).first()
    if not assignment:
        return

    threshold_query = db.query(umbrales_config).join(tipos_metrica).filter(
        umbrales_config.id_usuario == assignment.id_usuario,
        tipos_metrica.codigo == codigo_metrica,
    )
    if assignment.id_cultivo:
        threshold_query = threshold_query.filter(umbrales_config.id_cultivo == assignment.id_cultivo)
    threshold = threshold_query.first()
    if not threshold:
        return

    active_alerts = db.query(alertas).filter(
        alertas.id_usuario == assignment.id_usuario,
        alertas.id_asignacion == id_asignacion,
        alertas.id_tipo_metrica == threshold.id_tipo_metrica,
        alertas.estado.in_(ACTIVE_STATES),
    ).with_for_update().all()

    is_low = threshold.valor_minimo is not None and valor_actual < float(threshold.valor_minimo)
    is_high = threshold.valor_maximo is not None and valor_actual > float(threshold.valor_maximo)
    if not is_low and not is_high:
        _resolve_alerts(db, active_alerts, metric_name, unit, valor_actual, now)
        return

    type_id = low_type_id if is_low else high_type_id
    # Si la lectura cruzó directamente al extremo opuesto, cerrar la alerta anterior.
    opposite = [item for item in active_alerts if item.id_tipo_alerta != type_id]
    if opposite:
        _resolve_alerts(db, opposite, metric_name, unit, valor_actual, now)

    alert = next((item for item in active_alerts if item.id_tipo_alerta == type_id), None)
    alert_type = db.query(tipos_alerta).filter(tipos_alerta.id == type_id, tipos_alerta.activo.is_(True)).first()
    if not alert_type:
        return

    limit = float(threshold.valor_minimo if is_low else threshold.valor_maximo)
    sign = "<" if is_low else ">"
    message = (
        f"¡Alerta de {metric_name}! Valor detectado: {valor_actual:.2f}{unit} "
        f"(umbral: {sign} {limit:.2f}{unit})."
    )
    event_type = "recordatorio"
    if alert is None:
        alert = alertas(
            id_usuario=assignment.id_usuario,
            id_asignacion=id_asignacion,
            id_tipo_alerta=type_id,
            id_tipo_metrica=threshold.id_tipo_metrica,
            mensaje=message,
            prioridad="alta" if alert_type.severidad in {"critico", "critica", "emergencia"} else "media",
            valor_detectado=valor_actual,
            ultimo_valor_detectado=valor_actual,
            umbral=limit,
            estado="activa",
            fecha=now,
        )
        db.add(alert)
        db.flush()
        event_type = "activacion"
    else:
        alert.mensaje = message
        alert.ultimo_valor_detectado = valor_actual

    preference = db.query(configuracion_notificaciones).filter(
        configuracion_notificaciones.id_usuario == assignment.id_usuario,
        configuracion_notificaciones.id_tipo_alerta == type_id,
    ).first()
    _deliver(db, alert, alert_type, message, event_type, preference, now)
