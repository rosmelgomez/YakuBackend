import json

from src.main.service.irrigationServ import (
    DEFAULT_RELAY_MINUTES,
    MAX_RELAY_MINUTES,
    MIN_RELAY_MINUTES,
    build_relay_command,
    clamp_duration_seconds,
)


def test_relay_duration_is_clamped_to_safety_range():
    assert clamp_duration_seconds(None) == DEFAULT_RELAY_MINUTES * 60
    assert clamp_duration_seconds(1) == MIN_RELAY_MINUTES * 60
    assert clamp_duration_seconds(900) == 900
    assert clamp_duration_seconds(9999) == MAX_RELAY_MINUTES * 60


def test_on_command_carries_duration_and_off_does_not():
    on_payload = json.loads(build_relay_command("ON", 420))
    off_payload = json.loads(build_relay_command("OFF"))

    assert on_payload == {"accion": "ON", "duracion_seg": 420}
    assert off_payload == {"accion": "OFF"}


def test_firmware_has_local_timeout_and_accepts_timed_commands():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "esp32-sensor-proximidad.ino").read_text(encoding="utf-8")
    assert 'commandDoc["duracion_seg"]' in source
    assert "DURACION_RELE_MAX_SEG = 1800" in source
    assert 'motivoBomba = "tiempo_maximo"' in source
    assert 'motivoValvula = "tiempo_maximo_valvula"' in source


def test_irrigation_executions_lifecycle():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.main.model.models import (
        usuarios,
        dispositivos,
        asignaciones_iot,
        configuracion_control,
        configuracion_tanque,
        fuentes_agua,
        riego,
        ejecucion_riego,
        telemetria_tanque,
        tipos_dispositivo,
    )
    from src.main.service.irrigationServ import start_irrigation, stop_irrigation, resume_irrigation
    import datetime as dt

    engine = create_engine("sqlite:///:memory:")
    tables = [
        usuarios.__table__,
        tipos_dispositivo.__table__,
        dispositivos.__table__,
        fuentes_agua.__table__,
        asignaciones_iot.__table__,
        configuracion_control.__table__,
        configuracion_tanque.__table__,
        telemetria_tanque.__table__,
        riego.__table__,
        ejecucion_riego.__table__,
    ]
    for table in tables:
        table.create(engine)
    db = sessionmaker(bind=engine)()
    try:
        # Mock MQTT publishing to avoid network errors in test
        import src.main.service.irrigationServ as irr_module
        original_pub = irr_module._publish_relay_command
        irr_module._publish_relay_command = lambda assignment, payload: None
        original_status_pub = irr_module._publish_pump_status
        irr_module._publish_pump_status = lambda db_sess, session, state: None

        db.add(usuarios(id_usuario=1, nombre="Prueba", correo="prueba@example.com", contrasena="x"))
        db.add(tipos_dispositivo(id=2, nombre="actuador"))
        db.add(dispositivos(id_dispositivo=1, id_tipo=2, nombre="Actuador Bomba", client_id_mqtt="ESP32_Yaku_002"))
        db.add(fuentes_agua(id=1, id_usuario=1, nombre="Tanque Prueba", tipo="tanque", capacidad_litros=100.0, altura_tanque_cm=50.0, activo=True))
        db.add(asignaciones_iot(id=1, id_usuario=1, id_dispositivo=1, id_fuente_agua=1, activo=True))
        db.add(configuracion_tanque(id_asignacion=1, valvula_abierta=False, bomba_encendida=False))
        db.commit()

        # 1. Start irrigation (ON)
        now1 = dt.datetime(2026, 7, 4, 10, 0, 0)
        # Create initial telemetry to have an initial distance
        db.add(telemetria_tanque(id_asignacion=1, distancia_cm=10.0, bomba_encendida=False, fecha=now1))
        db.commit()

        session = start_irrigation(db, db.query(asignaciones_iot).one(), "manual", requested_seconds=300, now=now1)
        assert session.estado is False
        assert session.segundos_acumulados == 0
        
        # Verify execution was created
        execs = db.query(ejecucion_riego).filter(ejecucion_riego.id_riego == session.id).all()
        assert len(execs) == 1
        assert float(execs[0].distancia_inicial_cm) == 10.0
        assert execs[0].fecha_fin is None

        # 2. Pause irrigation (transient stop)
        now2 = dt.datetime(2026, 7, 4, 10, 2, 0) # 120 seconds later
        # Create telemetry at the end of the run with new distance
        db.add(telemetria_tanque(id_asignacion=1, distancia_cm=20.0, bomba_encendida=True, fecha=now2))
        db.commit()

        stop_irrigation(db, db.query(asignaciones_iot).one(), "sin_agua", now=now2)
        assert session.estado is False
        assert session.segundos_acumulados == 120
        # capacity=100.0, height=50.0 => 2 liters per cm. Delta = 20 - 10 = 10 cm. 10 * 2 = 20 liters.
        assert float(session.cantidad_agua_litros) == 20.0
        assert session.motivo_cierre == "pausado_sin_agua_120"

        # Verify execution was closed
        db.refresh(execs[0])
        assert execs[0].fecha_fin == now2
        assert float(execs[0].distancia_final_cm) == 20.0
        assert execs[0].duracion_segundos == 120
        assert float(execs[0].cantidad_agua_litros) == 20.0

        # 3. Resume irrigation (ON)
        now3 = dt.datetime(2026, 7, 4, 10, 5, 0)
        # Create telemetry before resuming to set new initial distance
        db.add(telemetria_tanque(id_asignacion=1, distancia_cm=15.0, bomba_encendida=False, fecha=now3))
        db.commit()

        resume_irrigation(db, db.query(asignaciones_iot).one(), session, now=now3)
        execs = db.query(ejecucion_riego).filter(ejecucion_riego.id_riego == session.id).order_by(ejecucion_riego.id.asc()).all()
        assert len(execs) == 2
        assert float(execs[1].distancia_inicial_cm) == 15.0
        assert execs[1].fecha_fin is None

        # 4. Final stop (OFF)
        now4 = dt.datetime(2026, 7, 4, 10, 7, 0) # 120 seconds later
        # Create telemetry at the end of the run
        db.add(telemetria_tanque(id_asignacion=1, distancia_cm=25.0, bomba_encendida=True, fecha=now4))
        db.commit()

        stop_irrigation(db, db.query(asignaciones_iot).one(), "manual", now=now4)
        assert session.estado is True
        assert session.segundos_acumulados == 240 # 120 + 120
        # Run 2 delta = 25 - 15 = 10 cm => 20 liters. Total liters = 20 + 20 = 40.0
        assert float(session.cantidad_agua_litros) == 40.0
        assert session.motivo_cierre == "manual"

        db.refresh(execs[1])
        assert execs[1].fecha_fin == now4
        assert float(execs[1].distancia_final_cm) == 25.0
        assert execs[1].duracion_segundos == 120
        assert float(execs[1].cantidad_agua_litros) == 20.0

        # Restore original functions
        irr_module._publish_relay_command = original_pub
        irr_module._publish_pump_status = original_status_pub
    finally:
        db.close()


def test_tank_refill_is_transient_pause():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.main.model.models import (
        usuarios,
        dispositivos,
        asignaciones_iot,
        configuracion_control,
        configuracion_tanque,
        fuentes_agua,
        riego,
        ejecucion_riego,
        telemetria_tanque,
        tipos_dispositivo,
    )
    from src.main.service.irrigationServ import remaining_seconds, start_irrigation, stop_irrigation
    import datetime as dt
    import src.main.service.irrigationServ as irr_module

    engine = create_engine("sqlite:///:memory:")
    tables = [
        usuarios.__table__,
        tipos_dispositivo.__table__,
        dispositivos.__table__,
        fuentes_agua.__table__,
        asignaciones_iot.__table__,
        configuracion_control.__table__,
        configuracion_tanque.__table__,
        telemetria_tanque.__table__,
        riego.__table__,
        ejecucion_riego.__table__,
    ]
    for table in tables:
        table.create(engine)

    db = sessionmaker(bind=engine)()
    try:
        original_pub = irr_module._publish_relay_command
        original_status_pub = irr_module._publish_pump_status
        irr_module._publish_relay_command = lambda assignment, payload: None
        irr_module._publish_pump_status = lambda db_sess, session, state: None

        db.add(usuarios(id_usuario=1, nombre="Prueba", correo="prueba@example.com", contrasena="x"))
        db.add(tipos_dispositivo(id=2, nombre="actuador"))
        db.add(dispositivos(id_dispositivo=1, id_tipo=2, nombre="Actuador Bomba", client_id_mqtt="ESP32_Yaku_002"))
        db.add(fuentes_agua(id=1, id_usuario=1, nombre="Tanque Prueba", tipo="tanque", capacidad_litros=100.0, altura_tanque_cm=50.0, activo=True))
        db.add(asignaciones_iot(id=1, id_usuario=1, id_dispositivo=1, id_fuente_agua=1, activo=True))
        db.add(configuracion_tanque(id_asignacion=1, valvula_abierta=False, bomba_encendida=False))
        db.commit()

        assignment = db.query(asignaciones_iot).one()
        start = dt.datetime(2026, 7, 4, 10, 0, 0)
        db.add(telemetria_tanque(id_asignacion=1, distancia_cm=10.0, bomba_encendida=False, fecha=start))
        db.commit()

        session = start_irrigation(db, assignment, "automatico_ml", requested_seconds=300, now=start)
        paused_at = dt.datetime(2026, 7, 4, 10, 2, 0)
        db.add(telemetria_tanque(id_asignacion=1, distancia_cm=18.0, bomba_encendida=True, fecha=paused_at))
        db.commit()

        stop_irrigation(db, assignment, "tanque_llenandose", now=paused_at)

        assert session.estado is False
        assert session.segundos_acumulados == 120
        assert session.motivo_cierre == "pausado_tanque_llenandose_120"
        assert remaining_seconds(session, paused_at) == 180
    finally:
        irr_module._publish_relay_command = original_pub
        irr_module._publish_pump_status = original_status_pub
        db.close()


def test_pause_can_use_esp32_reported_zero_seconds():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.main.model.models import (
        usuarios,
        dispositivos,
        asignaciones_iot,
        configuracion_control,
        configuracion_tanque,
        fuentes_agua,
        riego,
        ejecucion_riego,
        telemetria_tanque,
        tipos_dispositivo,
    )
    from src.main.service.irrigationServ import (
        pause_irrigation_session,
        remaining_seconds,
        start_irrigation,
    )
    import datetime as dt
    import src.main.service.irrigationServ as irr_module

    engine = create_engine("sqlite:///:memory:")
    tables = [
        usuarios.__table__,
        tipos_dispositivo.__table__,
        dispositivos.__table__,
        fuentes_agua.__table__,
        asignaciones_iot.__table__,
        configuracion_control.__table__,
        configuracion_tanque.__table__,
        telemetria_tanque.__table__,
        riego.__table__,
        ejecucion_riego.__table__,
    ]
    for table in tables:
        table.create(engine)

    db = sessionmaker(bind=engine)()
    try:
        original_pub = irr_module._publish_relay_command
        original_status_pub = irr_module._publish_pump_status
        irr_module._publish_relay_command = lambda assignment, payload: None
        irr_module._publish_pump_status = lambda db_sess, session, state: None

        db.add(usuarios(id_usuario=1, nombre="Prueba", correo="prueba@example.com", contrasena="x"))
        db.add(tipos_dispositivo(id=2, nombre="actuador"))
        db.add(dispositivos(id_dispositivo=1, id_tipo=2, nombre="Actuador Bomba", client_id_mqtt="ESP32_Yaku_002"))
        db.add(fuentes_agua(id=1, id_usuario=1, nombre="Tanque Prueba", tipo="tanque", capacidad_litros=100.0, altura_tanque_cm=50.0, activo=True))
        db.add(asignaciones_iot(id=1, id_usuario=1, id_dispositivo=1, id_fuente_agua=1, activo=True))
        db.add(configuracion_tanque(id_asignacion=1, valvula_abierta=False, bomba_encendida=False))
        db.commit()

        assignment = db.query(asignaciones_iot).one()
        start = dt.datetime(2026, 7, 4, 10, 0, 0)
        db.add(telemetria_tanque(id_asignacion=1, distancia_cm=7.02, bomba_encendida=False, fecha=start))
        db.commit()

        session = start_irrigation(db, assignment, "manual", requested_seconds=441, now=start)
        rejected_at = dt.datetime(2026, 7, 4, 10, 0, 5)
        pause_irrigation_session(
            db,
            session,
            "sensor_error",
            rejected_at,
            executed_seconds_override=0,
        )

        assert session.estado is False
        assert session.segundos_acumulados == 0
        assert session.motivo_cierre == "pausado_sensor_error_0"
        assert remaining_seconds(session, rejected_at) == 441
    finally:
        irr_module._publish_relay_command = original_pub
        irr_module._publish_pump_status = original_status_pub
        db.close()


def test_irrigation_blocked_when_valve_open():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.main.model.models import (
        asignaciones_iot,
        configuracion_tanque,
        dispositivos,
        ejecucion_riego,
        fuentes_agua,
        riego,
        tipos_dispositivo,
        usuarios,
    )
    import src.main.service.irrigationServ as irr_module
    from src.main.service.irrigationServ import start_irrigation, resume_irrigation
    import datetime as dt

    engine = create_engine("sqlite:///:memory:")
    tables = [
        usuarios.__table__,
        tipos_dispositivo.__table__,
        dispositivos.__table__,
        fuentes_agua.__table__,
        asignaciones_iot.__table__,
        configuracion_tanque.__table__,
        riego.__table__,
        ejecucion_riego.__table__
    ]
    for table in tables:
        table.create(engine)

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # Mock MQTT publishing to avoid actual network calls
        original_pub = irr_module._publish_relay_command
        original_status_pub = irr_module._publish_pump_status
        irr_module._publish_relay_command = lambda *args, **kwargs: None
        irr_module._publish_pump_status = lambda *args, **kwargs: None

        # Setup base objects
        db.add(usuarios(id_usuario=1, nombre="Prueba", correo="prueba@example.com", contrasena="x"))
        db.add(tipos_dispositivo(id=2, nombre="actuador"))
        db.add(dispositivos(id_dispositivo=1, id_tipo=2, nombre="Actuador Bomba", client_id_mqtt="ESP32_Yaku_002"))
        db.add(fuentes_agua(id=1, id_usuario=1, nombre="Tanque Prueba", tipo="tanque", capacidad_litros=100.0, altura_tanque_cm=50.0, activo=True))
        db.add(asignaciones_iot(id=1, id_usuario=1, id_dispositivo=1, id_fuente_agua=1, activo=True))
        db.add(configuracion_tanque(id_asignacion=1, valvula_abierta=True, bomba_encendida=False))
        db.commit()

        assignment = db.query(asignaciones_iot).one()

        # Test starting is blocked
        import pytest
        with pytest.raises(ValueError, match="el tanque se está rellenando"):
            start_irrigation(db, assignment, "manual")

        # Test resuming is blocked
        # Create a paused session to try to resume
        session = riego(id_asignacion=1, id_usuario=1, tipo_riego="manual", duracion_segundos=300, estado=False, motivo_cierre="pausado_sin_agua_120")
        db.add(session)
        db.commit()

        with pytest.raises(ValueError, match="el tanque se está rellenando"):
            resume_irrigation(db, assignment, session)

        # Restore original functions
        irr_module._publish_relay_command = original_pub
        irr_module._publish_pump_status = original_status_pub
    finally:
        db.close()
