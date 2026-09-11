import json
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from src.main.service import dispositivoServ as service


@pytest.mark.parametrize("active", [True, False])
def test_activation_sends_json_accepted_by_both_firmwares(monkeypatch, active):
    repo = service.data_repository
    device = NS(client_id_mqtt="ESP32_Yaku_002", nombre="Flujo")
    assignments = [NS(activo=not active), NS(activo=not active)]
    monkeypatch.setattr(repo, "queryProcesarActivacionDispositivoDispositivo", Mock(return_value=device))
    monkeypatch.setattr(repo, "queryProcesarActivacionDispositivoAsigQuery", Mock())
    monkeypatch.setattr(repo, "queryProcesarActivacionDispositivoAsigs", Mock(return_value=assignments))
    publish = Mock()
    monkeypatch.setattr(service, "publish_mqtt_message", publish)
    for name in ("add", "commit"):
        monkeypatch.setattr(service.session_repository, name, Mock())
    result = service.procesar_activacion_dispositivo(3, active, Mock(), NS(id_rol=1))
    assert result["active"] is active
    assert all(a.activo is active for a in assignments)
    topic, payload = publish.call_args.args
    assert topic == "yaku/dispositivo/ESP32_Yaku_002/config"
    assert json.loads(payload) == {"funcionamiento_activo": active}
    assert publish.call_args.kwargs == {"qos": 1, "retain": True}
