from sqlalchemy import func
from sqlalchemy.orm import Session

from src.main.model.models import alertas, notificaciones, tipos_alerta


def queryListNotificaciones(db: Session, id_usuario: int, limit: int = 30):
    dashboard_entregada = (
        db.query(notificaciones.id)
        .filter(
            notificaciones.id_alerta == alertas.id,
            notificaciones.canal == "dashboard",
            notificaciones.enviado.is_(True),
        )
        .exists()
    )
    return (
        db.query(alertas, tipos_alerta)
        .join(tipos_alerta, tipos_alerta.id == alertas.id_tipo_alerta)
        .filter(
            alertas.id_usuario == id_usuario,
            alertas.notificacion_eliminada.is_(False),
            dashboard_entregada,
        )
        .order_by(func.coalesce(alertas.ultima_notificacion_en, alertas.fecha).desc())
        .limit(limit)
        .all()
    )


def queryAlertaUsuario(db: Session, id_usuario: int, id_alerta: int):
    return (
        db.query(alertas)
        .filter(alertas.id == id_alerta, alertas.id_usuario == id_usuario)
        .first()
    )


def queryAlertasUsuarioQuery(db: Session, id_usuario: int):
    return db.query(alertas).filter(
        alertas.id_usuario == id_usuario, alertas.notificacion_eliminada.is_(False)
    )
