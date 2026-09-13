import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.main.model.models import (
    alertas,
    asignaciones_iot,
    configuracion_notificaciones,
    notificaciones,
    suscripciones_push,
    tipos_alerta,
    tipos_metrica,
    configuracion_umbrales,
    cultivos,
    riego,
    usuarios,
)
from src.main.service.notifications.alertEngineServ import (
    clamp_reminder_minutes,
    default_reminder_minutes,
    evaluar_y_disparar_alerta,
    notification_is_due,
    notificar_problema_riego,
    notificar_riego_ejecutado_ml,
    notificar_riego_finalizado,
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


def test_evaluar_y_disparar_alerta_does_not_generate_notifications():
    engine = create_engine("sqlite:///:memory:")
    tables = [
        usuarios.__table__, tipos_metrica.__table__, asignaciones_iot.__table__,
        configuracion_umbrales.__table__, tipos_alerta.__table__, alertas.__table__,
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
        db.add(configuracion_umbrales(id=1, id_usuario=1, id_cultivo=1, id_tipo_metrica=1, valor_minimo=20, valor_maximo=80))
        db.add(tipos_alerta(id=1, codigo="HUM_BAJA", nombre="Humedad baja", severidad="critico", activo=True))
        db.add(configuracion_notificaciones(
            id_usuario=1, id_tipo_alerta=1, activo=True,
            canal_email=True, canal_dashboard=True, recordatorio_minutos=15,
        ))
        db.commit()

        # No se deben generar alertas ni notificaciones cuando las 4 variables o tanque estén fuera de rango
        for metrica, valor in [
            ("HUM_SUELO", 10),
            ("HUM_AMB", 5),
            ("TEMP_AMB", 45),
            ("TEMP_SUELO", 40),
            ("NIVEL_AGUA", 5),
        ]:
            evaluar_y_disparar_alerta(db, 1, metrica, valor, now=dt.datetime(2026, 6, 20, 10, 0))

        assert db.query(alertas).count() == 0
        assert db.query(notificaciones).count() == 0
    finally:
        db.close()



def test_umbrales_excludes_tank_battery_and_flow_metrics():
    from src.main.repositories import dashboardRep
    from src.main.model.models import (
        usuarios, cultivos, tipos_metrica, configuracion_umbrales,
    )
    engine = create_engine("sqlite:///:memory:")
    tables = [
        usuarios.__table__, cultivos.__table__, tipos_metrica.__table__, configuracion_umbrales.__table__,
    ]
    for table in tables:
        table.create(engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(usuarios(id_usuario=1, nombre="Prueba", correo="prueba@example.com", contrasena="x"))
        db.add(cultivos(id_cultivo=1, id_usuario=1, nombre_planta="Tomate"))
        db.add_all([
            tipos_metrica(id=1, codigo="HUM_SUELO", nombre="Humedad de Suelo", unidad="%"),
            tipos_metrica(id=2, codigo="HUM_AMB", nombre="Humedad Ambiente", unidad="%"),
            tipos_metrica(id=3, codigo="TEMP_AMB", nombre="Temperatura Ambiente", unidad="°C"),
            tipos_metrica(id=4, codigo="TEMP_SUELO", nombre="Temperatura de Suelo", unidad="°C"),
            tipos_metrica(id=5, codigo="NIVEL_AGUA", nombre="Nivel de Tanque", unidad="%"),
            tipos_metrica(id=6, codigo="BAT_PCT", nombre="Nivel de Batería", unidad="%"),
            tipos_metrica(id=7, codigo="CAUDAL", nombre="Caudal de riego", unidad="L/min"),
        ])
        for m_id in range(1, 8):
            db.add(configuracion_umbrales(id=m_id, id_usuario=1, id_cultivo=1, id_tipo_metrica=m_id, valor_minimo=10, valor_maximo=90))
        db.commit()

        tipos = dashboardRep.queryObtenerDatosAlertasTipos(db)
        codigos_tipos = [t.codigo for t in tipos]
        assert "NIVEL_AGUA" not in codigos_tipos
        assert "BAT_PCT" not in codigos_tipos
        assert "CAUDAL" not in codigos_tipos
        assert set(codigos_tipos) == {"HUM_SUELO", "HUM_AMB", "TEMP_AMB", "TEMP_SUELO"}

        raw = dashboardRep.queryObtenerDatosAlertasUmbralesRaw(db, 1, 1)
        assert len(raw) == 4
        m_ids = [u.id_tipo_metrica for u in raw]
        assert 5 not in m_ids
        assert 6 not in m_ids
        assert 7 not in m_ids
    finally:
        db.close()


def test_notificar_riego_ejecutado_ml(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    tables = [
        usuarios.__table__, tipos_metrica.__table__, asignaciones_iot.__table__,
        configuracion_umbrales.__table__, tipos_alerta.__table__, alertas.__table__,
        configuracion_notificaciones.__table__, notificaciones.__table__,
        suscripciones_push.__table__,
    ]
    for table in tables:
        table.create(engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(usuarios(id_usuario=1, nombre="Prueba", correo="prueba@example.com", contrasena="x"))
        db.add(tipos_alerta(id=1, codigo="RIEGO_AUTO", nombre="Riego automático", severidad="info", activo=True))
        db.add(suscripciones_push(
            id=1, id_usuario=1, endpoint="https://example.com/push",
            key_p256dh="key1", key_auth="auth1", fecha_registro=dt.datetime.now()
        ))
        db.commit()

        pushed = []
        monkeypatch.setattr(
            "src.main.service.notifications.alertEngineServ.enviar_webpush",
            lambda info, title, msg: pushed.append((title, msg)) or True,
        )

        ws_broadcasts = []
        monkeypatch.setattr(
            "src.main.service.notifications.alertEngineServ._schedule_broadcast",
            lambda payload, user_id: ws_broadcasts.append((payload, user_id)),
        )

        datos_vars = {
            "humedad_suelo": 19.5,
            "humedad_ambiente": 42.0,
            "temperatura_ambiente": 27.5,
            "temperatura_suelo": 23.0,
        }

        notificar_riego_ejecutado_ml(
            db,
            id_usuario=1,
            id_cultivo=2,
            datos_variables=datos_vars,
            duracion_segundos=90,
            nombre_cultivo="Lechuga",
            id_asignacion=1,
        )

        # 1. Verificación WebSocket dentro de la app
        assert len(ws_broadcasts) == 1
        payload, uid = ws_broadcasts[0]
        assert uid == 1
        assert payload["event"] == "riego_iniciado"
        assert payload["duracion_segundos"] == 90
        assert payload["datos_variables"] == datos_vars
        assert "19.5%" in payload["mensaje"]
        assert "42.0%" in payload["mensaje"]
        assert "27.5°C" in payload["mensaje"]
        assert "23.0°C" in payload["mensaje"]

        # 2. Verificación base de datos (alertas y notificaciones dashboard)
        alert_db = db.query(alertas).first()
        assert alert_db is not None
        assert "Lechuga" in alert_db.mensaje
        assert "Humedad Suelo: 19.5%" in alert_db.mensaje

        notif_db = db.query(notificaciones).first()
        assert notif_db is not None
        assert notif_db.canal == "dashboard"
        assert notif_db.tipo_evento == "riego_ml"

        # 3. Verificación Web Push
        assert len(pushed) == 1
        title, body = pushed[0]
        assert title == "Riego activado por IA"
        assert "19.5%" in body
    finally:
        db.close()



def test_notificar_problema_riego(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    tables = [
        usuarios.__table__, tipos_metrica.__table__, asignaciones_iot.__table__,
        configuracion_umbrales.__table__, tipos_alerta.__table__, alertas.__table__,
        configuracion_notificaciones.__table__, notificaciones.__table__,
        suscripciones_push.__table__,
    ]
    for table in tables:
        table.create(engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(usuarios(id_usuario=1, nombre="Prueba", correo="prueba@example.com", contrasena="x"))
        db.add(suscripciones_push(
            id=1, id_usuario=1, endpoint="https://example.com/push",
            key_p256dh="key1", key_auth="auth1", fecha_registro=dt.datetime.now()
        ))
        alert = alertas(id=1, id_usuario=1, id_asignacion=1, id_tipo_alerta=1, id_tipo_metrica=1, mensaje="Test", estado="activa")
        db.add(alert)
        db.commit()

        pushed = []
        monkeypatch.setattr(
            "src.main.service.notifications.alertEngineServ.enviar_webpush",
            lambda info, title, msg: pushed.append((title, msg)) or True,
        )

        notificar_problema_riego(
            db, 1, "Riego fallido", "No se detectó flujo tras abrir la válvula.",
            severidad="critica", id_alerta=1
        )

        assert len(pushed) == 1
        assert pushed[0][0] == "Riego fallido"
        notif = db.query(notificaciones).filter(notificaciones.canal == "webpush").first()
        assert notif is not None
        assert notif.tipo_evento == "problema_riego"
    finally:
        db.close()


def test_notificar_riego_finalizado(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    tables = [
        usuarios.__table__, tipos_metrica.__table__, cultivos.__table__,
        asignaciones_iot.__table__, tipos_alerta.__table__, alertas.__table__,
        configuracion_notificaciones.__table__, notificaciones.__table__,
        suscripciones_push.__table__, riego.__table__,
    ]
    for table in tables:
        table.create(engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(usuarios(id_usuario=1, nombre="Prueba", correo="prueba@example.com", contrasena="x"))
        db.add(cultivos(id_cultivo=1, id_usuario=1, nombre_planta="Albahaca"))
        db.add(asignaciones_iot(id=1, id_usuario=1, id_dispositivo=1, id_cultivo=1, activo=True))
        tipo_ml = tipos_alerta(id=11, codigo="RIEGO_ML", nombre="Riego activado por IA", severidad="info", activo=True)
        db.add(tipo_ml)
        db.add(suscripciones_push(
            id=1, id_usuario=1, endpoint="https://example.com/push",
            key_p256dh="key1", key_auth="auth1", fecha_registro=dt.datetime.now()
        ))
        # Alerta activa previa de inicio de riego ML que debe resolverse al finalizar
        active_alert = alertas(
            id=1, id_usuario=1, id_asignacion=1, id_tipo_alerta=11,
            mensaje="Riego iniciado...", estado="activa", fecha=dt.datetime.now()
        )
        db.add(active_alert)

        sesion_riego = riego(
            id=1,
            id_asignacion=1,
            id_usuario=1,
            tipo_riego="automatico_ml",
            duracion_segundos=120,
            segundos_acumulados=120,
            cantidad_agua_litros=14.85,
            motivo_cierre="tiempo_maximo",
            estado=True,
        )
        db.add(sesion_riego)
        db.commit()

        pushed = []
        monkeypatch.setattr(
            "src.main.service.notifications.alertEngineServ.enviar_webpush",
            lambda info, title, msg: pushed.append((title, msg)) or True,
        )

        ws_broadcasts = []
        monkeypatch.setattr(
            "src.main.service.notifications.alertEngineServ._schedule_broadcast",
            lambda payload, user_id: ws_broadcasts.append((payload, user_id)),
        )

        notificar_riego_finalizado(db, sesion_riego, litros_usados=14.85)

        # 1. Verificación WebSocket
        assert len(ws_broadcasts) == 1
        payload, uid = ws_broadcasts[0]
        assert uid == 1
        assert payload["event"] == "riego_finalizado"
        assert payload["litros_usados"] == 14.85
        assert payload["duracion_segundos"] == 120
        assert "14.85 L" in payload["mensaje"]
        assert "Albahaca" in payload["mensaje"]

        # 2. Verificación de que la alerta activa previa fue resuelta
        prev_alert = db.query(alertas).filter(alertas.id == 1).first()
        assert prev_alert.estado == "resuelta"

        # 3. Verificación de alerta y notificación de finalización en DB
        new_alert = db.query(alertas).filter(alertas.id != 1).first()
        assert new_alert is not None
        assert new_alert.estado == "resuelta"
        assert "14.85 L" in new_alert.mensaje

        notif_db = db.query(notificaciones).filter(notificaciones.tipo_evento == "riego_finalizado").first()
        assert notif_db is not None
        assert notif_db.canal == "dashboard"
        assert "14.85 L" in notif_db.mensaje

        # 4. Verificación Web Push
        assert len(pushed) == 1
        title, body = pushed[0]
        assert title == "Riego finalizado"
        assert "14.85 L" in body
        assert "Albahaca" in body
    finally:
        db.close()




