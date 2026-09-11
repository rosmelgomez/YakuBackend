from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from src.main.dtos.firmwareDto import FirmwareInstallationCreate
from src.main.service import firmwareServ as service


@pytest.mark.parametrize("method,kind", [("flujometro", "riego_flujo"), ("proximidad", "riego")])
def test_installation_rejects_wrong_irrigation_firmware(monkeypatch, method, kind):
    device = NS(metodo_medicion=method)
    wrong = "riego" if kind == "riego_flujo" else "riego_flujo"
    firmware = NS(publicado=True, descontinuado=False, tipo_dispositivo=wrong)
    monkeypatch.setattr(service.data_repository, "queryCreateInstallationFirmware", Mock(return_value=firmware))
    monkeypatch.setattr(service.data_repository, "queryCreateInstallationDevice", Mock(return_value=device))
    add = Mock()
    monkeypatch.setattr(service.session_repository, "add", add)
    with pytest.raises(HTTPException) as exc:
        service.create_installationServ(FirmwareInstallationCreate(id_firmware=1, id_dispositivo=1), Mock(), NS(id_rol=1))
    assert exc.value.status_code == 409
    add.assert_not_called()


@pytest.mark.parametrize("method,kind", [("flujometro", "riego_flujo"), ("proximidad", "riego")])
def test_installation_accepts_matching_firmware(monkeypatch, method, kind):
    monkeypatch.setattr(service.data_repository, "queryCreateInstallationFirmware", Mock(return_value=NS(publicado=True, descontinuado=False, tipo_dispositivo=kind)))
    monkeypatch.setattr(service.data_repository, "queryCreateInstallationDevice", Mock(return_value=NS(metodo_medicion=method)))
    for name in ("add", "commit", "refresh"):
        monkeypatch.setattr(service.session_repository, name, Mock())
    result = service.create_installationServ(FirmwareInstallationCreate(id_firmware=1,id_dispositivo=2), Mock(), NS(id_rol=1,id_usuario=1))
    assert result.id_dispositivo == 2
    assert result.estado == "iniciada"


def test_flow_map_does_not_invent_water_level():
    assignment = NS(id=9, tipo_metrica=NS(codigo="CAUDAL"), componente=None, pin_gpio=27, id_componente=1)
    device = NS(tipo=NS(nombre="ESP32 Actuador con flujometro"), metodo_medicion="flujometro")
    metric_map, _ = service.build_assignment_metric_map([assignment], device)
    assert metric_map == {"CAUDAL": 9}


def test_proximity_sensor_name_is_not_classified_as_collector():
    assert service.firmware_type_for_device(NS(tipo=NS(nombre="Actuador con sensor de proximidad"))) == "riego"
