from sqlalchemy.orm import Session

from src.main.model.models import (
    alertas,
    asignaciones_iot,
    configuracion_notificaciones,
    configuracion_umbrales,
    notificaciones,
    suscripciones_push,
    tipos_alerta,
    tipos_metrica,
    usuarios,
)


def queryLastAttemptRow(db: Session, alert_id, channel):
    return (
        db.query(notificaciones)
        .filter(notificaciones.id_alerta == alert_id, notificaciones.canal == channel)
        .order_by(notificaciones.id.desc())
        .first()
    )


def queryRecordNotificationPreviousAttempts(db: Session, channel, event_type, alert):
    return (
        db.query(notificaciones)
        .filter(
            notificaciones.id_alerta == alert.id,
            notificaciones.canal == channel,
            notificaciones.tipo_evento == event_type,
        )
        .count()
    )


def queryDeliverSuscripcionesPush(db: Session, alert):
    return (
        db.query(suscripciones_push)
        .filter(suscripciones_push.id_usuario == alert.id_usuario)
        .all()
    )


def queryDeliverUser(db: Session, alert):
    return db.query(usuarios).filter(usuarios.id_usuario == alert.id_usuario).first()


def queryResolveAlertsAlertType(db: Session, alert):
    return (
        db.query(tipos_alerta).filter(tipos_alerta.id == alert.id_tipo_alerta).first()
    )


def queryResolveAlertsPreference(db: Session, alert):
    return (
        db.query(configuracion_notificaciones)
        .filter(
            configuracion_notificaciones.id_usuario == alert.id_usuario,
            configuracion_notificaciones.id_tipo_alerta == alert.id_tipo_alerta,
        )
        .first()
    )


def queryEvaluarYDispararAlertaAssignment(db: Session, id_asignacion):
    return (
        db.query(asignaciones_iot).filter(asignaciones_iot.id == id_asignacion).first()
    )


def queryEvaluarYDispararAlertaThresholdQuery(db: Session, codigo_metrica, assignment):
    return (
        db.query(configuracion_umbrales)
        .join(tipos_metrica)
        .filter(
            configuracion_umbrales.id_usuario == assignment.id_usuario,
            tipos_metrica.codigo == codigo_metrica,
        )
    )


def queryEvaluarYDispararAlertaThresholdQuery2(threshold_query, assignment):
    return threshold_query.filter(
        configuracion_umbrales.id_cultivo == assignment.id_cultivo
    )


def queryEvaluarYDispararAlertaThreshold(threshold_query):
    return threshold_query.first()


def queryEvaluarYDispararAlertaActiveAlerts(
    db: Session, id_asignacion, ACTIVE_STATES, assignment, threshold
):
    return (
        db.query(alertas)
        .filter(
            alertas.id_usuario == assignment.id_usuario,
            alertas.id_asignacion == id_asignacion,
            alertas.id_tipo_metrica == threshold.id_tipo_metrica,
            alertas.estado.in_(ACTIVE_STATES),
        )
        .with_for_update()
        .all()
    )


def queryEvaluarYDispararAlertaAlertType(db: Session, type_id):
    return (
        db.query(tipos_alerta)
        .filter(tipos_alerta.id == type_id, tipos_alerta.activo.is_(True))
        .first()
    )


def queryEvaluarYDispararAlertaPreference(db: Session, type_id, assignment):
    return (
        db.query(configuracion_notificaciones)
        .filter(
            configuracion_notificaciones.id_usuario == assignment.id_usuario,
            configuracion_notificaciones.id_tipo_alerta == type_id,
        )
        .first()
    )


def queryFirstTipoAlerta(db: Session):
    return db.query(tipos_alerta).filter(tipos_alerta.activo.is_(True)).first()


def queryTipoAlertaRiegoMl(db: Session):
    tipo = (
        db.query(tipos_alerta)
        .filter(tipos_alerta.codigo == "RIEGO_ML", tipos_alerta.activo.is_(True))
        .first()
    )
    if not tipo:
        tipo = db.query(tipos_alerta).filter(tipos_alerta.activo.is_(True)).first()
    return tipo


def queryTipoAlertaProblemaRiego(db: Session):
    tipo = (
        db.query(tipos_alerta)
        .filter(tipos_alerta.codigo == "PROBLEMA_RIEGO", tipos_alerta.activo.is_(True))
        .first()
    )
    if not tipo:
        tipo = db.query(tipos_alerta).filter(tipos_alerta.activo.is_(True)).first()
    return tipo


def querySuscripcionesPushUsuario(db: Session, id_usuario: int):
    return (
        db.query(suscripciones_push)
        .filter(suscripciones_push.id_usuario == id_usuario)
        .all()
    )


def queryActiveRiegoMlAlerts(db: Session, id_usuario: int, id_asignacion: int):
    tipo = queryTipoAlertaRiegoMl(db)
    if not tipo:
        return []
    return (
        db.query(alertas)
        .filter(
            alertas.id_usuario == id_usuario,
            alertas.id_asignacion == id_asignacion,
            alertas.id_tipo_alerta == tipo.id,
            alertas.estado == "activa",
        )
        .all()
    )



