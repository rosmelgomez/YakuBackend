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
