import datetime as dt
import logging

from sqlalchemy.orm import Session

from src.main.repositories import alertEngineRep as data_repository
from src.main.repositories import sessionRep as session_repository

logger = logging.getLogger(__name__)

from src.main.model.models import (
    alertas,
    notificaciones,
    riego,
    suscripciones_push,
)
from src.main.service.notifications.emailServ import enviar_correo_alerta
from src.main.service.notifications.webpushServ import enviar_webpush
from src.main.service.notifications.websocketManagerServ import broadcast_ws_event

ACTIVE_STATES = ("pendiente", "activa")
METRIC_INFO = {
    "HUM_SUELO": ("Humedad de suelo", "%", 1, 2),
    "TEMP_SUELO": ("Temperatura de suelo", "°C", 3, 4),
    "TEMP_AMB": ("Temperatura ambiente", "°C", 5, 6),
    "HUM_AMB": ("Humedad ambiente", "%", 7, 8),
    "NIVEL_AGUA": ("Nivel del tanque", "%", 9, 10),
}


def default_reminder_minutes(severity: str | None) -> int:
    return (
        15 if (severity or "").lower() in {"critico", "critica", "emergencia"} else 30
    )


def clamp_reminder_minutes(value: int | None, severity: str | None) -> int:
    if value is None:
        return default_reminder_minutes(severity)
    return max(5, min(1440, int(value)))


def notification_is_due(
    last_sent: dt.datetime | None, now: dt.datetime, minutes: int
) -> bool:
    return last_sent is None or now >= last_sent + dt.timedelta(minutes=minutes)


def _schedule_broadcast(payload: dict, user_id: int) -> None:
    # broadcast_ws_event ya resuelve de forma segura si esto corre en el
    # loop principal de FastAPI o en un hilo externo (p. ej. el callback
    # de paho-mqtt al notificar un riego ejecutado por ML).
    broadcast_ws_event(payload, user_id)


def _last_attempt(db: Session, alert_id: int, channel: str) -> dt.datetime | None:
    row = data_repository.queryLastAttemptRow(db, alert_id, channel)
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
    previous_attempts = data_repository.queryRecordNotificationPreviousAttempts(
        db, channel, event_type, alert
    )
    session_repository.add(
        db,
        notificaciones(
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
        ),
    )


def _deliver(
    db: Session,
    alert,
    alert_type,
    message: str,
    event_type: str,
    preference,
    now: dt.datetime,
) -> None:
    dashboard_enabled = preference.canal_dashboard if preference else False
    email_enabled = preference.canal_email if preference else False
    push_enabled = bool(getattr(preference, "canal_push", False)) if preference else False
    preference_enabled = preference.activo if preference else False
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

    # Canal: Dentro de la app (Historial de riegos, inicio y finalización, alertas, recuperaciones y cambios de estado)
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
            "severidad": "info"
            if event_type == "recuperacion"
            else (
                "critica"
                if alert_type.severidad in {"critico", "critica", "emergencia"}
                else "advertencia"
            ),
            "valor": float(alert.ultimo_valor_detectado or alert.valor_detectado or 0),
            "tipo_evento": event_type,
        }
        _schedule_broadcast(payload, alert.id_usuario)

    # Canal: Push del dispositivo, con permiso
    push_due = not is_reminder or notification_is_due(
        _last_attempt(db, alert.id, "webpush"), now, reminder_minutes
    )
    if push_enabled and push_due:
        delivered = True
        for subscription in data_repository.queryDeliverSuscripcionesPush(db, alert):
            result = enviar_webpush(
                {
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.key_p256dh,
                        "auth": subscription.key_auth,
                    },
                },
                subject,
                message,
            )
            if result == "EXPIRED":
                session_repository.delete(db, subscription)
            else:
                _record_notification(
                    db,
                    alert,
                    "webpush",
                    subject,
                    message,
                    event_type,
                    result is True,
                    None
                    if result is True
                    else "El proveedor Web Push rechazó el envío",
                )

    # Canal: Correo (Verificación de cuenta, recuperación de contraseña y avisos importantes de seguridad)
    # No se satura con lecturas de umbrales periódicos de sensores.
    email_minutes = max(60, reminder_minutes)
    email_due = not is_reminder or notification_is_due(
        _last_attempt(db, alert.id, "email"), now, email_minutes
    )
    if email_enabled and email_due:
        user = data_repository.queryDeliverUser(db, alert)
        if user and user.correo:
            delivered = True
            body = (
                f"Hola {user.nombre},\n\n{message}\n\n"
                "Ingresa al panel de Yaku para revisar el estado del cultivo.\n\nEquipo Yaku"
            )
            success = enviar_correo_alerta(user.correo, f"YAKU: {subject}", body)
            _record_notification(
                db,
                alert,
                "email",
                f"YAKU: {subject}",
                body,
                event_type,
                success,
                None
                if success
                else "Error en el servidor de correo o destinatario rechazado",
            )

    if delivered:
        alert.ultima_notificacion_en = now
        alert.proxima_notificacion_en = now + dt.timedelta(minutes=reminder_minutes)
        alert.cantidad_notificaciones = int(alert.cantidad_notificaciones or 0) + 1
    session_repository.commit(db)


def _resolve_alerts(
    db: Session,
    active_alerts: list,
    metric_name: str,
    unit: str,
    value: float,
    now: dt.datetime,
) -> None:
    for alert in active_alerts:
        alert_type = data_repository.queryResolveAlertsAlertType(db, alert)
        if not alert_type:
            continue
        alert.estado = "resuelta"
        alert.resuelta_en = now
        alert.ultimo_valor_detectado = value
        alert.mensaje = f"{metric_name} volvió al rango normal: {value:.2f}{unit}."
        preference = data_repository.queryResolveAlertsPreference(db, alert)
        _deliver(db, alert, alert_type, alert.mensaje, "recuperacion", preference, now)


def evaluar_y_disparar_alerta(
    db: Session,
    id_asignacion: int,
    codigo_metrica: str,
    valor_actual: float,
    *,
    now: dt.datetime | None = None,
) -> None:
    """Las alertas de notificación por umbrales fuera de rango para las 4 variables
    (humedad suelo, humedad ambiente, temp ambiente, temp suelo) y tanque han sido desactivadas.
    El sistema únicamente notifica ejecuciones de riego por IA con los datos de las variables."""
    return


def is_push_enabled_for_user(db: Session, id_usuario: int, codigo_alerta: str) -> bool:
    """Verifica si el usuario tiene habilitado el canal push para el tipo de alerta indicado.
    Si no tiene configuración explícita guardada, se considera habilitado (True) por defecto."""
    from src.main.model.models import configuracion_notificaciones, tipos_alerta

    try:
        pref = (
            db.query(configuracion_notificaciones)
            .join(
                tipos_alerta,
                tipos_alerta.id == configuracion_notificaciones.id_tipo_alerta,
            )
            .filter(
                configuracion_notificaciones.id_usuario == id_usuario,
                tipos_alerta.codigo == codigo_alerta,
            )
            .first()
        )
        if pref is not None:
            return bool(pref.canal_push)
        return True
    except Exception as exc:
        logger.warning(
            f"Error verificando preferencia push para usuario {id_usuario}: {exc}"
        )
        return True


def notificar_riego_ejecutado_ml(
    db: Session,
    id_usuario: int,
    id_cultivo: int,
    datos_variables: dict,
    duracion_segundos: int,
    nombre_cultivo: str = "Cultivo",
    id_asignacion: int | None = None,
) -> None:
    """Notifica la ejecución de un riego decidido por el modelo ML,
    indicando explícitamente los datos de las 4 variables con que se ejecutó."""
    now = dt.datetime.now()
    hs = float(datos_variables.get("humedad_suelo") or 0.0)
    ha = float(datos_variables.get("humedad_ambiente") or 0.0)
    ta = float(datos_variables.get("temperatura_ambiente") or 0.0)
    ts = float(datos_variables.get("temperatura_suelo") or 0.0)

    titulo = "Riego activado por IA"
    mensaje = (
        f"Riego iniciado para {nombre_cultivo}. "
        f"Variables ML: Humedad Suelo: {hs:.1f}%, Humedad Amb: {ha:.1f}%, "
        f"Temp Amb: {ta:.1f}°C, Temp Suelo: {ts:.1f}°C. "
        f"Duración: {duracion_segundos}s."
    )

    # 1. Dentro de la app (WebSocket para alerta visual inmediata e historial reactivo)
    payload = {
        "id": f"riego-ml-{int(now.timestamp())}",
        "tipo": "control_update",
        "event": "riego_iniciado",
        "titulo": titulo,
        "mensaje": mensaje,
        "severidad": "info",
        "id_usuario": id_usuario,
        "id_cultivo": id_cultivo,
        "datos_variables": {
            "humedad_suelo": hs,
            "humedad_ambiente": ha,
            "temperatura_ambiente": ta,
            "temperatura_suelo": ts,
        },
        "duracion_segundos": duracion_segundos,
        "fecha": now.strftime("%H:%M"),
    }
    _schedule_broadcast(payload, id_usuario)

    # 2. Persistencia en alertas de la app si hay tipos_alerta disponibles
    nueva_alerta_id = None
    try:
        tipo_alerta_obj = data_repository.queryTipoAlertaRiegoMl(db)
        if tipo_alerta_obj:
            nueva_alerta = alertas(
                id_usuario=id_usuario,
                id_asignacion=id_asignacion,
                id_tipo_alerta=tipo_alerta_obj.id,
                mensaje=mensaje,
                prioridad="media",
                valor_detectado=hs,
                ultimo_valor_detectado=hs,
                umbral=0.0,
                estado="activa",
                fecha=now,
            )
            session_repository.add(db, nueva_alerta)
            session_repository.flush(db)
            nueva_alerta_id = nueva_alerta.id

            session_repository.add(
                db,
                notificaciones(
                    id_alerta=nueva_alerta.id,
                    id_usuario=id_usuario,
                    canal="dashboard",
                    asunto=titulo,
                    mensaje=mensaje,
                    enviado=True,
                    enviado_en=now,
                    tipo_evento="riego_ml",
                    intento=1,
                    intentado_en=now,
                ),
            )
    except Exception as db_exc:
        logger.warning(f"No se pudo registrar alerta de riego ML en DB: {db_exc}")

    # 3. Push del dispositivo (con permiso del usuario)
    if is_push_enabled_for_user(db, id_usuario, "RIEGO_ML"):
        subs = data_repository.querySuscripcionesPushUsuario(db, id_usuario)
        for sub in subs:
            result = enviar_webpush(
                {
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.key_p256dh,
                        "auth": sub.key_auth,
                    },
                },
                titulo,
                mensaje,
            )
            if result == "EXPIRED":
                session_repository.delete(db, sub)
            elif nueva_alerta_id:
                session_repository.add(
                    db,
                    notificaciones(
                        id_alerta=nueva_alerta_id,
                        id_usuario=id_usuario,
                        canal="webpush",
                        asunto=titulo,
                        mensaje=mensaje,
                        enviado=result is True,
                        enviado_en=now if result is True else None,
                        error=None if result is True else "Error en envío push",
                        tipo_evento="riego_ml",
                        intento=1,
                        intentado_en=now,
                    ),
                )

    session_repository.commit(db)


def notificar_riego_finalizado(
    db: Session,
    session: riego,
    litros_usados: float,
) -> None:
    """Notifica la finalización de un ciclo de riego, indicando explícitamente
    los litros consumidos en este riego (no acumulados diarios) y la duración."""
    if not session or not session.id_usuario:
        return

    now = dt.datetime.now()
    id_usuario = session.id_usuario
    duracion_segundos = int(
        session.duracion_segundos or session.segundos_acumulados or 0
    )
    litros = round(float(litros_usados or 0.0), 2)

    # 1. Obtener cultivo y asignación
    nombre_cultivo = "Cultivo"
    id_cultivo = None
    if session.id_asignacion:
        asig = data_repository.queryEvaluarYDispararAlertaAssignment(
            db, session.id_asignacion
        )
        if asig:
            id_cultivo = asig.id_cultivo
            if asig.cultivo and getattr(asig.cultivo, "nombre_planta", None):
                nombre_cultivo = asig.cultivo.nombre_planta

    titulo = "Riego finalizado"
    mensaje = (
        f"Riego finalizado para {nombre_cultivo}. "
        f"Agua consumida en este riego: {litros:.2f} L. "
        f"Duración: {duracion_segundos}s."
    )

    # 2. Dentro de la app (WebSocket para reactividad inmediata)
    payload = {
        "id": f"riego-fin-{int(now.timestamp())}",
        "tipo": "control_update",
        "event": "riego_finalizado",
        "titulo": titulo,
        "mensaje": mensaje,
        "severidad": "info",
        "id_usuario": id_usuario,
        "id_cultivo": id_cultivo,
        "litros_usados": litros,
        "duracion_segundos": duracion_segundos,
        "motivo_cierre": getattr(session, "motivo_cierre", "completado"),
        "fecha": now.strftime("%H:%M"),
    }
    _schedule_broadcast(payload, id_usuario)

    # 3. Resolver alertas activas de riego ML para esta asignación
    try:
        active_alerts = data_repository.queryActiveRiegoMlAlerts(
            db, id_usuario, session.id_asignacion
        )
        for act_al in active_alerts:
            act_al.estado = "resuelta"
            act_al.resuelta_en = now
            session_repository.add(db, act_al)
    except Exception as resolve_exc:
        logger.warning(
            f"No se pudieron resolver alertas activas de riego ML: {resolve_exc}"
        )

    # 4. Registrar alerta finalizada en el historial y registrar notificación
    nueva_alerta_id = None
    try:
        tipo_alerta_obj = data_repository.queryTipoAlertaRiegoMl(db)
        if tipo_alerta_obj:
            nueva_alerta = alertas(
                id_usuario=id_usuario,
                id_asignacion=session.id_asignacion,
                id_tipo_alerta=tipo_alerta_obj.id,
                mensaje=mensaje,
                prioridad="baja",
                valor_detectado=litros,
                ultimo_valor_detectado=litros,
                umbral=0.0,
                estado="resuelta",
                fecha=now,
                resuelta_en=now,
            )
            session_repository.add(db, nueva_alerta)
            session_repository.flush(db)
            nueva_alerta_id = nueva_alerta.id

            session_repository.add(
                db,
                notificaciones(
                    id_alerta=nueva_alerta.id,
                    id_usuario=id_usuario,
                    canal="dashboard",
                    asunto=titulo,
                    mensaje=mensaje,
                    enviado=True,
                    enviado_en=now,
                    tipo_evento="riego_finalizado",
                    intento=1,
                    intentado_en=now,
                ),
            )
    except Exception as db_exc:
        logger.warning(
            f"No se pudo registrar alerta de riego finalizado en DB: {db_exc}"
        )

    # 5. Push del dispositivo (con permiso del usuario)
    if is_push_enabled_for_user(db, id_usuario, "RIEGO_ML"):
        subs = data_repository.querySuscripcionesPushUsuario(db, id_usuario)
        for sub in subs:
            result = enviar_webpush(
                {
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.key_p256dh,
                        "auth": sub.key_auth,
                    },
                },
                titulo,
                mensaje,
            )
            if result == "EXPIRED":
                session_repository.delete(db, sub)
            elif nueva_alerta_id:
                session_repository.add(
                    db,
                    notificaciones(
                        id_alerta=nueva_alerta_id,
                        id_usuario=id_usuario,
                        canal="webpush",
                        asunto=titulo,
                        mensaje=mensaje,
                        enviado=result is True,
                        enviado_en=now if result is True else None,
                        error=None if result is True else "Error en envío push",
                        tipo_evento="riego_finalizado",
                        intento=1,
                        intentado_en=now,
                    ),
                )

    session_repository.commit(db)


def notificar_problema_riego(
    db: Session,
    id_usuario: int,
    titulo: str,
    mensaje: str,
    *,
    severidad: str = "critica",
    id_alerta: int | None = None,
) -> None:
    """Envía notificación inmediata dentro de la app (WebSocket) y Push al dispositivo
    ante problemas que requieren atención: riego fallido, interrupción, parada sin confirmar o desconexión durante el riego."""
    # 1. Dentro de la app (WebSocket)
    payload = {
        "tipo": "control_update",
        "event": "problema_riego",
        "titulo": titulo,
        "mensaje": mensaje,
        "severidad": severidad,
        "id_usuario": id_usuario,
    }
    _schedule_broadcast(payload, id_usuario)

    # Si no se pasó id_alerta, registrarla para persistencia en historial
    if not id_alerta:
        try:
            tipo_alerta_obj = data_repository.queryTipoAlertaProblemaRiego(db)
            if tipo_alerta_obj:
                nueva_alerta = alertas(
                    id_usuario=id_usuario,
                    id_tipo_alerta=tipo_alerta_obj.id,
                    mensaje=mensaje,
                    prioridad=severidad,
                    estado="activa",
                    fecha=dt.datetime.now(),
                )
                session_repository.add(db, nueva_alerta)
                session_repository.flush(db)
                id_alerta = nueva_alerta.id

                session_repository.add(
                    db,
                    notificaciones(
                        id_alerta=id_alerta,
                        id_usuario=id_usuario,
                        canal="dashboard",
                        asunto=titulo,
                        mensaje=mensaje,
                        enviado=True,
                        enviado_en=dt.datetime.now(),
                        tipo_evento="problema_riego",
                        intento=1,
                        intentado_en=dt.datetime.now(),
                    ),
                )
        except Exception as db_err:
            logger.warning(
                f"No se pudo crear registro de alerta para problema de riego: {db_err}"
            )

    # 2. Push del dispositivo, con permiso del usuario
    if is_push_enabled_for_user(db, id_usuario, "PROBLEMA_RIEGO"):
        subs = data_repository.querySuscripcionesPushUsuario(db, id_usuario)
        for sub in subs:
            result = enviar_webpush(
                {
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.key_p256dh,
                        "auth": sub.key_auth,
                    },
                },
                titulo,
                mensaje,
            )
            if result == "EXPIRED":
                session_repository.delete(db, sub)
            elif id_alerta:
                session_repository.add(
                    db,
                    notificaciones(
                        id_alerta=id_alerta,
                        id_usuario=id_usuario,
                        canal="webpush",
                        asunto=titulo,
                        mensaje=mensaje,
                        enviado=result is True,
                        enviado_en=dt.datetime.now() if result is True else None,
                        error=None if result is True else "El proveedor Web Push rechazó el envío",
                        tipo_evento="problema_riego",
                        intento=1,
                        intentado_en=dt.datetime.now(),
                    ),
                )
    session_repository.commit(db)


