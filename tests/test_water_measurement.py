from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.main.dtos.dispositivoDto import DispositivoCreate
from src.main.dtos.telemetriaDto import TelemetriaTanqueModel
from src.main.model import models as m
from src.main.service import dispositivoServ, irrigationServ, telemetriaServ
from src.main.service.deviceHealthServ import _is_actuator_device, _is_sensor_device


@pytest.fixture
def water_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    for model in (
        m.usuarios, m.tipos_dispositivo, m.dispositivos, m.fuentes_agua,
        m.cultivos, m.asignaciones_iot, m.tipos_metrica, m.configuracion_tanque,
        m.configuracion_control, m.telemetria_tanque, m.riego, m.ejecucion_riego,
    ):
        model.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    db.add(m.usuarios(id_usuario=1, nombre="Prueba", correo="water@example.test", contrasena="x"))
    db.add_all([
        m.tipos_dispositivo(id=2, nombre="Actuador proximidad", metodo_medicion="proximidad"),
        m.tipos_dispositivo(id=3, nombre="Actuador flujometro", metodo_medicion="flujometro"),
    ])
    db.commit()
    monkeypatch.setattr(irrigationServ, "_publish_relay_command", lambda *args: None)
    monkeypatch.setattr(irrigationServ, "_publish_pump_status", lambda *args: None)
    monkeypatch.setattr(telemetriaServ.data_repository, "queryCrearTelemetriaTanqueUsrMod", lambda *args: None)
    monkeypatch.setattr(telemetriaServ.data_repository, "queryCrearTelemetriaTanqueProgramacionesHoy", lambda *args: [])
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def install(db, method):
    device = dispositivoServ.registrar_dispositivoServ(
        DispositivoCreate(id_tipo=3 if method == "flujometro" else 2, nombre="Actuador prueba"),
        db, SimpleNamespace(id_rol=1),
    )
    assert device.metodo_medicion == method
    source = m.fuentes_agua(
        id=1, id_usuario=1, nombre="Fuente", tipo="conexion_directa" if method == "flujometro" else "tanque",
        altura_tanque_cm=None if method == "flujometro" else 50,
        capacidad_litros=None if method == "flujometro" else 100,
    )
    db.add(source)
    assignment = m.asignaciones_iot(id=1, id_dispositivo=device.id, id_usuario=1, id_fuente_agua=1, activo=True)
    db.add(assignment)
    db.add(m.configuracion_tanque(id_asignacion=1, bomba_encendida=False, valvula_abierta=False))
    db.commit()
    return assignment


def test_flow_readings_and_final_volume_are_persisted(water_db):
    db = water_db
    assignment = install(db, "flujometro")
    def report(on, volume, pulses):
        data = TelemetriaTanqueModel(
            id_asignacion=1, metodo_medicion="flujometro", estado_bomba=on,
            litros_riego=volume, litros_acumulados=volume, caudal_l_min=1.5,
            pulsos_riego=pulses, pulsos_por_litro=450,
            motivo_cierre="tiempo_maximo" if on == "OFF" else None,
        )
        return telemetriaServ.crear_telemetria_tanque(db=db, **data.model_dump(exclude={"tiempo_restante_seg"}))

    report("OFF", 0, 0)
    session = irrigationServ.start_irrigation(db, assignment, "manual", 120)
    report("ON", 0, 0)
    mid = report("ON", 1.2345, 556)
    report("OFF", 2.5, 1125)
    report("OFF", 2.5, 1125)  # Un OFF repetido no suma el volumen nuevamente.
    db.expire_all()
    stored = db.get(m.telemetria_tanque, mid.id)
    assert float(stored.litros_riego) == 1.2345
    assert float(stored.caudal_l_min) == 1.5
    assert stored.pulsos_riego == 556
    assert float(stored.pulsos_por_litro) == 450
    assert stored.distancia_cm is None and stored.porcentaje_nivel is None
    assert stored.metodo_medicion == "flujometro"
    execution = db.query(m.ejecucion_riego).one()
    assert execution.metodo_medicion == "flujometro"
    assert float(execution.cantidad_agua_litros) == 2.5
    assert float(db.get(m.riego, session.id).cantidad_agua_litros) == 2.5


def test_proximity_uses_entire_level_change_not_last_sample(water_db):
    db = water_db
    assignment = install(db, "proximidad")
    telemetriaServ.crear_telemetria_tanque(db, 1, 10, "OFF")
    session = irrigationServ.start_irrigation(db, assignment, "manual", 120)
    telemetriaServ.crear_telemetria_tanque(db, 1, 10, "ON")
    telemetriaServ.crear_telemetria_tanque(db, 1, 20, "ON", litros_riego=999)
    telemetriaServ.crear_telemetria_tanque(db, 1, 25, "OFF", motivo_cierre="tiempo_maximo")
    db.expire_all()
    assert float(db.get(m.riego, session.id).cantidad_agua_litros) == 30
    assert all(row.litros_riego is None for row in db.query(m.telemetria_tanque))


def test_registered_method_cannot_be_overridden_by_payload(water_db):
    install(water_db, "proximidad")
    with pytest.raises(ValueError, match="no coincide"):
        telemetriaServ.crear_telemetria_tanque(water_db, 1, None, "ON", litros_riego=2, metodo_medicion="flujometro")
    assert water_db.query(m.telemetria_tanque).count() == 0


def test_negative_volume_is_rejected_by_database(water_db):
    water_db.add(m.telemetria_tanque(id_asignacion=1, metodo_medicion="flujometro", litros_riego=-1))
    with pytest.raises(IntegrityError):
        water_db.flush()
    water_db.rollback()


@pytest.mark.parametrize("field,value", [("caudal_l_min", -1), ("pulsos_riego", -1), ("pulsos_por_litro", 0), ("litros_acumulados", float("inf"))])
def test_invalid_flow_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        TelemetriaTanqueModel(id_asignacion=1, estado_bomba="ON", **{field: value})


def test_unknown_device_type_cannot_be_registered(water_db):
    with pytest.raises(HTTPException) as error:
        dispositivoServ.registrar_dispositivoServ(DispositivoCreate(id_tipo=999, nombre="Error"), water_db, SimpleNamespace(id_rol=1))
    assert error.value.status_code == 400


@pytest.mark.parametrize("method", ["proximidad", "flujometro"])
def test_both_registered_types_are_actuators(water_db, method):
    assignment = install(water_db, method)
    assignment.dispositivo.tipo.nombre = "Actuador con sensor de medicion"
    assert _is_actuator_device(assignment.dispositivo)
    assert not _is_sensor_device(assignment.dispositivo)


def test_flow_actuator_rejects_assignment_to_tank(water_db):
    db = water_db
    device = dispositivoServ.registrar_dispositivoServ(
        DispositivoCreate(id_tipo=3, nombre="Flujometro"), db, SimpleNamespace(id_rol=1)
    )
    db.add(m.fuentes_agua(id=1, id_usuario=1, nombre="Tanque", tipo="tanque", capacidad_litros=100, altura_tanque_cm=50))
    db.add(m.cultivos(id_cultivo=1, id_usuario=1, id_fuente_agua=1, nombre_planta="Lechuga"))
    db.commit()
    with pytest.raises(HTTPException) as error:
        dispositivoServ.asignar_dispositivo_a_cultivoServ(device.id, 1, 1, db, SimpleNamespace(id_rol=1))
    assert error.value.status_code == 400
    assert "conexion_directa" in error.value.detail
    assert device.estado == "disponible"


@pytest.mark.parametrize("category", ["pantalla", "actuador"])
def test_register_and_assign_output_without_measurement(water_db, category):
    from src.main.dtos.dispositivoDto import ComponenteCreate, AsignarComponentePayload
    db = water_db
    m.tipos_componente.__table__.create(db.get_bind())
    m.componentes.__table__.create(db.get_bind())
    db.add(m.tipos_componente(id=1, nombre_modelo="Salida", categoria=category))
    db.add(m.dispositivos(id_dispositivo=1, id_tipo=3, nombre="Flujo", estado="asignado"))
    db.add(m.asignaciones_iot(id=1, id_usuario=1, id_dispositivo=1, activo=False))
    db.commit()
    admin = SimpleNamespace(id_rol=1)
    component = dispositivoServ.registrar_componenteServ(ComponenteCreate(id_tipo_componente=1), db, admin)
    assert component.en_almacen is True
    payload = AsignarComponentePayload(id_dispositivo=1, id_componente=component.id, pin_gpio=13)
    result = dispositivoServ.asignar_componente_dispositivoServ(payload, db, admin)
    assert result["status"] == "ok"
    assert component.en_almacen is False
    assignment = db.get(m.asignaciones_iot, result["id_asignacion"])
    assert assignment.id_tipo_metrica is None
    expected = 1 if category == "actuador" else 0
    assert db.query(m.configuracion_tanque).count() == expected
    dispositivoServ.asignar_componente_dispositivoServ(payload, db, admin)
    assert db.query(m.configuracion_tanque).count() == expected


def test_crear_telemetria_tanque_falls_back_when_no_source_configured(water_db):
    db = water_db
    db.add(m.dispositivos(id_dispositivo=10, id_tipo=1, nombre="Disp sin metodo", estado="asignado"))
    db.add(m.asignaciones_iot(id=10, id_usuario=1, id_dispositivo=10, activo=True))
    db.commit()

    reg = telemetriaServ.crear_telemetria_tanque(db, 10, distancia_cm=15.0, estado_bomba="OFF")
    assert reg.metodo_medicion == "proximidad"
    assert float(reg.distancia_cm) == 15.0

