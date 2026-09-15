from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from src.main.dtos.telemetriaDto import TelemetriaTanqueModel
from src.main.service import firmwareServ, telemetriaServ
from src.main.service import irrigationServ


@pytest.mark.parametrize("kind", ["manguera", "tanque"])
def test_provisioning_preserves_selected_source(kind):
    source = SimpleNamespace(tipo=kind, altura_tanque_cm=50 if kind == "tanque" else None, altura_seguridad_cm=None)
    assignment = SimpleNamespace(fuente_agua=source)
    result = firmwareServ.build_tank_config([assignment], Mock())
    assert result["tipo_fuente"] == kind


def test_direct_provisioning_uses_device_command_topic(monkeypatch):
    repo = firmwareServ.data_repository
    device = SimpleNamespace(
        mac_address=None, client_id_mqtt="YAKU-DIRECT-1",
        topic_pub="yaku/tanque/datos", topic_sub="yaku/riego/comando",
        metodo_medicion="flujometro",
    )
    assignment = SimpleNamespace(id_usuario=1, id_cultivo=2)
    monkeypatch.setattr(firmwareServ, "require_admin", Mock())
    monkeypatch.setattr(repo, "queryGetProvisioningDevice", Mock(return_value=device))
    monkeypatch.setattr(repo, "queryGetProvisioningAssignments", Mock(return_value=[assignment]))
    monkeypatch.setattr(repo, "queryGetProvisioningFarmer", Mock(return_value=None))
    monkeypatch.setattr(repo, "queryGetProvisioningCrop", Mock(return_value=None))
    monkeypatch.setattr(firmwareServ, "build_assignment_metric_map", Mock(return_value=({"NIVEL_AGUA": 3}, [])))
    monkeypatch.setattr(firmwareServ, "build_tank_config", Mock(return_value={"tipo_fuente": "manguera"}))
    monkeypatch.setenv("ML_IRRIGATION_COOLDOWN_MINUTES", "60")
    result = firmwareServ.get_provisioningServ(1, Mock(), Mock())
    assert result["tipo_fuente"] == "manguera"
    assert result["mqtt"]["topic_sub"] == "yaku/dispositivo/YAKU-DIRECT-1/comando"
    assert device.topic_sub == result["mqtt"]["topic_sub"]


@pytest.mark.parametrize("liters", [-1, float("nan"), float("inf")])
def test_invalid_measured_volume_is_rejected(liters):
    with pytest.raises(ValidationError):
        TelemetriaTanqueModel(
            id_asignacion=1, distancia_cm=-1, estado_bomba="OFF", litros_riego=liters
        )


@pytest.mark.parametrize("from_crop", [False, True])
def test_direct_stop_records_flow_volume_without_tank_level(monkeypatch, from_crop):
    repo = telemetriaServ.data_repository
    # Keep the test independent of PostgreSQL and exercise the service's stop path.
    for name in dir(repo):
        if name.startswith("queryCrearTelemetriaTanque"):
            monkeypatch.setattr(repo, name, Mock(return_value=None))
    source = SimpleNamespace(tipo="manguera", altura_tanque_cm=None, capacidad_litros=None)
    assignment = SimpleNamespace(
        id=1, id_fuente_agua=None if from_crop else 7,
        cultivo=SimpleNamespace(fuente_agua=source) if from_crop else None,
    )
    repo.queryCrearTelemetriaTanqueAsig.return_value = assignment
    repo.queryCrearTelemetriaTanqueFuente.return_value = source
    repo.queryCrearTelemetriaTanqueUltimoRegistro.return_value = SimpleNamespace(bomba_encendida=True)
    session = SimpleNamespace(motivo_cierre=None, fecha=datetime.now())
    repo.queryCrearTelemetriaTanqueRiegoActivo3.return_value = session
    finish = Mock()
    monkeypatch.setattr(telemetriaServ, "complete_irrigation_session", finish)

    result = telemetriaServ.crear_telemetria_tanque(
        Mock(), 1, -1, "OFF", valvula_abierta=False,
        motivo_cierre="tiempo_maximo", litros_riego=2.75,
    )

    assert result.distancia_cm is None
    assert result.metodo_medicion == "flujometro"
    assert result.litros_riego == 2.75
    assert result.nivel_agua_cm is None
    assert result.porcentaje_nivel is None
    assert result.estado_nivel == "no_aplica"
    assert result.valvula_abierta is False
    assert finish.call_args.args[-1] == 2.75


def test_server_stop_preserves_latest_flow_measurement(monkeypatch):
    execution = SimpleNamespace(
        fecha_inicio=datetime.now(), distancia_inicial_cm=-1,
        cantidad_agua_litros=3.25,
    )
    repo = irrigationServ.data_repository
    monkeypatch.setattr(repo, "queryCloseActiveExecutionExecution", Mock(return_value=execution))
    monkeypatch.setattr(repo, "queryCloseActiveExecutionLastTel", Mock(return_value=SimpleNamespace(distancia_cm=-1)))
    monkeypatch.setattr(irrigationServ, "_find_sensor_assignment_id", Mock(return_value=1))
    volume = irrigationServ._close_active_execution(
        Mock(), SimpleNamespace(id_asignacion=1), "usuario", datetime.now()
    )
    assert volume == 3.25
    assert execution.cantidad_agua_litros == 3.25


def test_obtener_datos_control_direct_water(monkeypatch):
    from src.main.service import controlServ
    repo = controlServ.data_repository

    source = SimpleNamespace(id=10, nombre="Red Directa", tipo="conexion_directa")
    crop = SimpleNamespace(id=5, fuente_agua=source)
    device = SimpleNamespace(
        id_dispositivo=20, nombre="Actuador Flujo", estado="activo",
        ultimo_ping=datetime.now(), id_tipo=3, mac_address="AA:BB:CC:DD:EE:FF",
        tipo=SimpleNamespace(nombre="ESP32 Actuador con flujometro", metodo_medicion="flujometro"),
        metodo_medicion="flujometro"
    )
    assignment = SimpleNamespace(id=1, pin_gpio=25, id_dispositivo=20, activo=True, id_componente=None)
    tank_config = SimpleNamespace(bomba_encendida=False, valvula_abierta=False)

    monkeypatch.setattr(repo, "queryObtenerDatosControlUsuario", Mock(return_value=SimpleNamespace(zona_horaria="UTC")))
    monkeypatch.setattr(repo, "queryObtenerDatosControlRol", Mock(return_value=SimpleNamespace(nombre="Agricultor")))
    monkeypatch.setattr(repo, "queryObtenerDatosControlAsigs", Mock(return_value=[assignment]))
    monkeypatch.setattr(repo, "queryObtenerDatosControlConfigT", Mock(return_value=tank_config))
    monkeypatch.setattr(repo, "queryObtenerDatosControlDev", Mock(return_value=device))
    monkeypatch.setattr(repo, "queryObtenerDatosControlDev2", Mock(return_value=device))
    monkeypatch.setattr(repo, "queryObtenerDatosControlTipo", Mock(return_value=device.tipo))
    monkeypatch.setattr(repo, "queryObtenerDatosControlCultivo", Mock(return_value=crop))
    monkeypatch.setattr(repo, "queryObtenerDatosControlConfigC", Mock(return_value=None))
    monkeypatch.setattr(repo, "queryObtenerDatosControlUsrMod", Mock(return_value=None))
    monkeypatch.setattr(repo, "queryObtenerDatosControlDefaultModel", Mock(return_value=None))
    monkeypatch.setattr(repo, "queryObtenerDatosControlDefaultModel2", Mock(return_value=None))
    monkeypatch.setattr(repo, "queryObtenerDatosControlSysLogs", Mock(return_value=[]))
    monkeypatch.setattr(repo, "queryObtenerDatosControlUltimaPred", Mock(return_value=None))
    monkeypatch.setattr(repo, "queryObtenerDatosControlUltimaSesion", Mock(return_value=None))
    monkeypatch.setattr(repo, "queryObtenerDatosControlSesionPausada", Mock(return_value=None))
    monkeypatch.setattr(repo, "queryObtenerDatosControlSesionActiva", Mock(return_value=None))
    monkeypatch.setattr(controlServ, "get_max_relay_seconds", Mock(return_value=600))

    db_mock = Mock()
    data = controlServ.obtener_datos_control(db_mock, 1, 5, 2)
    assert data["esConexionDirecta"] is True
    assert data["fuenteAgua"]["tipo"] == "conexion_directa"
    assert data["actuadorTipo"]["metodoMedicion"] == "flujometro"
    assert data["modo"]["actual"] == "Predictivo (ML)"
    assert data["modo"]["predictivoActivo"] is True
    assert data["horarios"] == []


def test_obtener_litros_acumulados_asignacion(monkeypatch):
    from src.main.service import irrigationServ
    repo = irrigationServ.data_repository
    monkeypatch.setattr(repo, "queryGetLitrosAcumuladosAsignacion", Mock(return_value=12.5))
    total = irrigationServ.obtener_litros_acumulados_asignacion(Mock(), 1)
    assert total == 12.5


def test_direct_irrigation_does_not_pause_on_zero_flow(monkeypatch):
    """Direct connection valve remains active when flow pauses (caudal = 0)."""
    repo = telemetriaServ.data_repository
    for name in dir(repo):
        if name.startswith("queryCrearTelemetriaTanque"):
            monkeypatch.setattr(repo, name, Mock(return_value=None))

    source = SimpleNamespace(tipo="conexion_directa", altura_tanque_cm=None, capacidad_litros=None)
    assignment = SimpleNamespace(
        id=1, id_fuente_agua=10, id_usuario=1, id_cultivo=5,
        cultivo=SimpleNamespace(fuente_agua=source),
    )
    repo.queryCrearTelemetriaTanqueAsig.return_value = assignment
    repo.queryCrearTelemetriaTanqueFuente.return_value = source
    repo.queryCrearTelemetriaTanqueUltimoRegistro.return_value = SimpleNamespace(bomba_encendida=True)

    session = SimpleNamespace(
        id=1, duracion_segundos=600, segundos_acumulados=30,
        motivo_cierre=None, fecha=datetime.now(), estado=False,
    )
    execution = SimpleNamespace(
        id=1, metodo_medicion="flujometro", distancia_inicial_cm=None,
        cantidad_agua_litros=1.25,
    )
    repo.queryCrearTelemetriaTanqueRiegoActivo2.return_value = session
    repo.queryCrearTelemetriaTanqueEjecucionAbierta2.return_value = execution

    pause_mock = Mock()
    complete_mock = Mock()
    monkeypatch.setattr(telemetriaServ, "pause_irrigation_session", pause_mock)
    monkeypatch.setattr(telemetriaServ, "complete_irrigation_session", complete_mock)

    db_mock = Mock()
    result = telemetriaServ.crear_telemetria_tanque(
        db_mock,
        id_asignacion=1,
        distancia_cm=-1,
        estado_bomba="ON",
        valvula_abierta=False,
        motivo_cierre=None,
        duracion_objetivo_seg=600,
        tiempo_ejecutado_seg=45,
        litros_riego=1.25,
        caudal_l_min=0.0,
    )

    assert result.bomba_encendida is True
    assert result.metodo_medicion == "flujometro"
    assert session.estado is False
    assert session.motivo_cierre is None
    assert session.segundos_acumulados == 45
    assert execution.cantidad_agua_litros == 1.25
    pause_mock.assert_not_called()
    complete_mock.assert_not_called()


def test_direct_irrigation_ignores_sin_flujo_closure(monkeypatch):
    """Direct connection does not pause or stop on sin_flujo."""
    repo = telemetriaServ.data_repository
    for name in dir(repo):
        if name.startswith("queryCrearTelemetriaTanque"):
            monkeypatch.setattr(repo, name, Mock(return_value=None))

    source = SimpleNamespace(tipo="conexion_directa", altura_tanque_cm=None, capacidad_litros=None)
    assignment = SimpleNamespace(
        id=1, id_fuente_agua=10, id_usuario=1, id_cultivo=5,
        cultivo=SimpleNamespace(fuente_agua=source),
    )
    repo.queryCrearTelemetriaTanqueAsig.return_value = assignment
    repo.queryCrearTelemetriaTanqueFuente.return_value = source
    repo.queryCrearTelemetriaTanqueUltimoRegistro.return_value = SimpleNamespace(bomba_encendida=True)

    session = SimpleNamespace(
        id=1, duracion_segundos=600, segundos_acumulados=30,
        motivo_cierre=None, fecha=datetime.now(), estado=False,
    )
    repo.queryCrearTelemetriaTanqueRiegoActivo3.return_value = session

    pause_mock = Mock()
    complete_mock = Mock()
    monkeypatch.setattr(telemetriaServ, "pause_irrigation_session", pause_mock)
    monkeypatch.setattr(telemetriaServ, "complete_irrigation_session", complete_mock)

    db_mock = Mock()
    telemetriaServ.crear_telemetria_tanque(
        db_mock,
        id_asignacion=1,
        distancia_cm=-1,
        estado_bomba="OFF",
        valvula_abierta=False,
        motivo_cierre="sin_flujo",
        duracion_objetivo_seg=600,
        tiempo_ejecutado_seg=30,
        litros_riego=1.25,
    )

    pause_mock.assert_not_called()
    complete_mock.assert_not_called()


def test_flow_firmware_has_no_sin_flujo_timeout():
    """El caudal y la conectividad no pueden interrumpir el ciclo temporizado."""
    from pathlib import Path
    sketch_path = Path(__file__).resolve().parents[1] / "esp32-sensor-flujo.ino"
    code = sketch_path.read_text(encoding="utf-8")
    assert "SIN_FLUJO_MS" not in code
    assert 'cerrarRiego("sin_flujo")' not in code
    assert 'cerrarRiego("conexion_perdida")' not in code
    assert 'if (ahora - inicioMs >= duracionMs) cerrarRiego("tiempo_maximo")' in code

