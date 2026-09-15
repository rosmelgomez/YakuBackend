from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.main.model.models import configuracion_control, usuarios, cultivos
from src.main.service.irrigationServ import get_ml_cooldown_minutes
from src.main.service.controlServ import actualizar_cooldown_riego
import pytest

def test_ml_cooldown_retrieval_and_update():
    engine = create_engine('sqlite:///:memory:')
    tables = [
        usuarios.__table__,
        cultivos.__table__,
        configuracion_control.__table__,
    ]
    for table in tables:
        table.drop(engine, checkfirst=True)
        table.create(engine, checkfirst=True)

    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE logs_sistema (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario INTEGER,
                accion VARCHAR(100) NOT NULL,
                modulo VARCHAR(50),
                descripcion TEXT,
                ip_acceso VARCHAR(45),
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        '''))

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(usuarios(id_usuario=1, nombre='Prueba', correo='p@ex.com', contrasena='x'))
        db.add(cultivos(id_cultivo=1, id_usuario=1, nombre_planta='Tomate'))
        db.commit()

        # By default without configuracion_control, fallback is 30
        assert get_ml_cooldown_minutes(db, 1, 1) == 30

        # Update cooldown to 45
        res = actualizar_cooldown_riego(db, 1, 1, 45)
        assert res['status'] == 'ok'
        assert res['cooldownMinutos'] == 45
        assert get_ml_cooldown_minutes(db, 1, 1) == 45

        # Boundary checks
        with pytest.raises(ValueError, match='entre 1 y 1440'):
            actualizar_cooldown_riego(db, 1, 1, 0)
        with pytest.raises(ValueError, match='entre 1 y 1440'):
            actualizar_cooldown_riego(db, 1, 1, 1441)
    finally:
        db.close()


def test_ml_cooldown_blocked_when_actuator_active():
    from src.main.model.models import asignaciones_iot, configuracion_tanque, dispositivos, tipos_dispositivo, riego
    engine = create_engine('sqlite:///:memory:')
    tables = [
        usuarios.__table__,
        tipos_dispositivo.__table__,
        dispositivos.__table__,
        cultivos.__table__,
        configuracion_control.__table__,
        asignaciones_iot.__table__,
        configuracion_tanque.__table__,
        riego.__table__,
    ]
    for table in tables:
        table.drop(engine, checkfirst=True)
        table.create(engine, checkfirst=True)

    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE logs_sistema (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario INTEGER,
                accion VARCHAR(100) NOT NULL,
                modulo VARCHAR(50),
                descripcion TEXT,
                ip_acceso VARCHAR(45),
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        '''))

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(usuarios(id_usuario=1, nombre='Prueba', correo='p@ex.com', contrasena='x'))
        tipo = tipos_dispositivo(id=2, nombre='ESP32_ACTUADOR')
        db.add(tipo)
        db.flush()
        dev = dispositivos(id_dispositivo=1, id_tipo=2, nombre='ESP32', estado='activo')
        db.add(dev)
        db.add(cultivos(id_cultivo=1, id_usuario=1, nombre_planta='Tomate'))
        db.flush()

        asig = asignaciones_iot(
            id=10,
            id_usuario=1,
            id_dispositivo=1,
            id_cultivo=1,
            activo=True,
        )
        db.add(asig)
        db.flush()

        tank_cfg = configuracion_tanque(
            id_asignacion=10,
            bomba_encendida=False,
            valvula_abierta=False,
        )
        db.add(tank_cfg)
        db.commit()

        # 1. Actuator is active in standby (bomba_encendida=False) -> permitted!
        res = actualizar_cooldown_riego(db, 1, 1, 60)
        assert res['status'] == 'ok'
        assert res['cooldownMinutos'] == 60

        # 2. Irrigation in progress (bomba_encendida=True) -> blocked!
        tank_cfg.bomba_encendida = True
        db.commit()

        with pytest.raises(ValueError, match='Bloqueado: no se puede modificar el tiempo de cooldown mientras el riego está en curso.'):
            actualizar_cooldown_riego(db, 1, 1, 45)

        # 3. Trying to turn off actuator during active irrigation -> raises HTTPException 400!
        from fastapi import HTTPException
        from src.main.service.dispositivoServ import actualizar_funcionamiento_usuario
        user_mock = type("User", (), {"id_usuario": 1, "id_rol": 2})()
        with pytest.raises(HTTPException) as exc_info:
            actualizar_funcionamiento_usuario(1, False, db, user_mock)
        assert exc_info.value.status_code == 400
        assert "No se puede apagar el dispositivo actuador mientras hay un riego en curso" in exc_info.value.detail
    finally:
        db.close()


def test_cooldown_activation_respects_cooldown():
    from datetime import datetime, timezone, timedelta
    from src.main.model.models import asignaciones_iot, configuracion_tanque, dispositivos, tipos_dispositivo, riego, cultivo_modelo
    from src.main.service.dispositivoServ import actualizar_funcionamiento_usuario
    engine = create_engine('sqlite:///:memory:')
    tables = [
        usuarios.__table__,
        tipos_dispositivo.__table__,
        dispositivos.__table__,
        cultivos.__table__,
        configuracion_control.__table__,
        asignaciones_iot.__table__,
        configuracion_tanque.__table__,
        riego.__table__,
        cultivo_modelo.__table__,
    ]
    for table in tables:
        table.drop(engine, checkfirst=True)
        table.create(engine, checkfirst=True)

    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE logs_sistema (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario INTEGER,
                accion VARCHAR(100) NOT NULL,
                modulo VARCHAR(50),
                descripcion TEXT,
                ip_acceso VARCHAR(45),
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        '''))

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(usuarios(id_usuario=1, nombre='Prueba', correo='p@ex.com', contrasena='x'))
        tipo_sensor = tipos_dispositivo(id=1, nombre='ESP32_SENSOR')
        db.add(tipo_sensor)
        tipo = tipos_dispositivo(id=2, nombre='ESP32_ACTUADOR')
        db.add(tipo)
        db.flush()
        dev_sensor = dispositivos(id_dispositivo=2, id_tipo=1, nombre='ESP32_S', estado='activo', funcionamiento_activo=True)
        db.add(dev_sensor)
        dev = dispositivos(id_dispositivo=1, id_tipo=2, nombre='ESP32', estado='activo', funcionamiento_activo=False)
        db.add(dev)
        db.add(cultivos(id_cultivo=1, id_usuario=1, nombre_planta='Tomate'))
        db.flush()

        asig_sensor = asignaciones_iot(
            id=11,
            id_usuario=1,
            id_dispositivo=2,
            id_cultivo=1,
            activo=True,
        )
        db.add(asig_sensor)

        asig = asignaciones_iot(
            id=10,
            id_usuario=1,
            id_dispositivo=1,
            id_cultivo=1,
            activo=False,
        )
        db.add(asig)
        db.flush()

        tank_cfg = configuracion_tanque(
            id_asignacion=10,
            bomba_encendida=False,
            valvula_abierta=False,
        )
        db.add(tank_cfg)
        # Cooldown is 30 minutes
        cfg_ctrl = configuracion_control(
            id_usuario=1,
            id_cultivo=1,
            cooldown_minutos=30,
            duracion_riego_max_seg=600,
        )
        db.add(cfg_ctrl)

        # Previous irrigation finished 25 minutes ago
        prev_riego = riego(
            id_asignacion=10,
            id_usuario=1,
            tipo_riego="automatico_ml",
            estado=True,
            fecha_inicio=now - timedelta(minutes=35),
            fecha_fin=now - timedelta(minutes=25),
            fecha=now - timedelta(minutes=35),
        )
        db.add(prev_riego)

        # Active ML model mode
        usr_mod = cultivo_modelo(
            id_usuario=1,
            id_cultivo=1,
            id_modelo=1,
            activo=True,
        )
        db.add(usr_mod)
        db.commit()

        # Activating the device when 25 min elapsed < 30 min cooldown
        # should NOT trigger immediate irrigation
        user_mock = type("User", (), {"id_usuario": 1, "id_rol": 2})()
        actualizar_funcionamiento_usuario(1, True, db, user_mock)

        # Confirm no new irrigation was started
        total_riegos = db.query(riego).count()
        assert total_riegos == 1
    finally:
        db.close()


def test_ml_model_selection_blocked_when_actuator_active():
    from fastapi import HTTPException
    from src.main.model.models import asignaciones_iot, configuracion_tanque, dispositivos, tipos_dispositivo, modelos_ml, cultivo_modelo, historial_modelos
    from src.main.service.mlServ import seleccionar_modeloServ

    engine = create_engine('sqlite:///:memory:')
    tables = [
        usuarios.__table__,
        tipos_dispositivo.__table__,
        dispositivos.__table__,
        cultivos.__table__,
        configuracion_control.__table__,
        asignaciones_iot.__table__,
        configuracion_tanque.__table__,
        modelos_ml.__table__,
        cultivo_modelo.__table__,
        historial_modelos.__table__,
    ]
    for table in tables:
        table.drop(engine, checkfirst=True)
        table.create(engine, checkfirst=True)

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(usuarios(id_usuario=1, nombre='Prueba', correo='p@ex.com', contrasena='x'))
        tipo = tipos_dispositivo(id=2, nombre='ESP32_ACTUADOR')
        db.add(tipo)
        db.flush()
        dev = dispositivos(id_dispositivo=1, id_tipo=2, nombre='ESP32', estado='activo', funcionamiento_activo=True)
        db.add(dev)
        db.add(cultivos(id_cultivo=1, id_usuario=1, nombre_planta='Tomate'))
        db.add(modelos_ml(id_modelo=1, nombre_modelo='RandomForest', algoritmo='RandomForest', version='1.0', estado='activo', precision_modelo=0.95))
        db.add(modelos_ml(id_modelo=2, nombre_modelo='XGBoost', algoritmo='XGBoost', version='1.0', estado='activo', precision_modelo=0.92))
        db.flush()

        asig = asignaciones_iot(
            id=10,
            id_usuario=1,
            id_dispositivo=1,
            id_cultivo=1,
            activo=True,
        )
        db.add(asig)
        db.commit()

        user_mock = type("User", (), {"id_usuario": 1, "id_rol": 2})()

        # Actuator is active -> selecting model is BLOCKED with 400
        with pytest.raises(HTTPException) as exc_info:
            seleccionar_modeloServ(id_modelo_ml=2, id_cultivo=1, db=db, current_user=user_mock)
        assert exc_info.value.status_code == 400
        assert "Bloqueado: no se puede cambiar el modelo" in exc_info.value.detail

        # Actuator is inactive -> selecting model is PERMITTED
        asig.activo = False
        db.commit()

        res = seleccionar_modeloServ(id_modelo_ml=2, id_cultivo=1, db=db, current_user=user_mock)
        assert res["status"] == "ok"
        assert res["model_id"] == 2
    finally:
        db.close()