import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
from src.services.notifications.alert_engine import (
    clamp_reminder_minutes,
    default_reminder_minutes,
    evaluar_y_disparar_alerta,
    notification_is_due,
)


def test_default_frequency_depends_on_severity():
    assert default_reminder_minutes("critico") == 15
    assert default_reminder_minutes("emergencia") == 15
    assert default_reminder_minutes("advertencia") == 30


def test_user_frequency_is_limited_to_safe_range():
    assert clamp_reminder_minutes(1, "critico") == 5
    assert clamp_reminder_minutes(45, "critico") == 45
    assert clamp_reminder_minutes(9999, "advertencia") == 1440


def test_reminder_is_not_due_before_interval():
    sent_at = dt.datetime(2026, 6, 20, 10, 0)
    assert not notification_is_due(sent_at, dt.datetime(2026, 6, 20, 10, 14), 15)
    assert notification_is_due(sent_at, dt.datetime(2026, 6, 20, 10, 15), 15)
    assert notification_is_due(None, sent_at, 15)


def test_alert_is_reused_and_resolved_when_metric_recovers():
    engine = create_engine("sqlite:///:memory:")
    tables = [
        usuarios.__table__, tipos_metrica.__table__, asignaciones_iot.__table__,
        umbrales_config.__table__, tipos_alerta.__table__, alertas.__table__,
        configuracion_notificaciones.__table__, notificaciones.__table__,
        suscripciones_push.__table__,
    ]
    for table in tables:
        table.create(engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(usuarios(id_usuario=1, nombre="Prueba", correo="prueba@example.com", contrasena="x"))
        db.add(tipos_metrica(id=1, codigo="HUM_SUELO", nombre="Humedad", unidad="%"))
        db.add(asignaciones_iot(id=1, id_usuario=1, id_dispositivo=1, id_cultivo=1, id_tipo_metrica=1))
        db.add(umbrales_config(id=1, id_usuario=1, id_cultivo=1, id_tipo_metrica=1, valor_minimo=20, valor_maximo=80))
        db.add_all([
            tipos_alerta(id=1, codigo="HUM_BAJA", nombre="Humedad baja", severidad="critico", activo=True),
            tipos_alerta(id=2, codigo="HUM_ALTA", nombre="Humedad alta", severidad="advertencia", activo=True),
        ])
        db.add(configuracion_notificaciones(
            id_usuario=1, id_tipo_alerta=1, activo=True,
            canal_email=False, canal_dashboard=False, recordatorio_minutos=15,
        ))
        db.commit()

        evaluar_y_disparar_alerta(db, 1, "HUM_SUELO", 10, now=dt.datetime(2026, 6, 20, 10, 0))
        evaluar_y_disparar_alerta(db, 1, "HUM_SUELO", 9, now=dt.datetime(2026, 6, 20, 10, 1))
        assert db.query(alertas).count() == 1
        current = db.query(alertas).one()
        assert current.estado == "activa"
        assert float(current.ultimo_valor_detectado) == 9

        evaluar_y_disparar_alerta(db, 1, "HUM_SUELO", 50, now=dt.datetime(2026, 6, 20, 10, 2))
        db.refresh(current)
        assert current.estado == "resuelta"
        assert current.resuelta_en == dt.datetime(2026, 6, 20, 10, 2)
    finally:
        db.close()
