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


def test_procesar_mensaje_tanque_unassigned_omitted_without_warning(monkeypatch, caplog):
    import logging
    from unittest.mock import MagicMock
    from src.main.service import mqttServ

    mock_db = MagicMock()
    monkeypatch.setattr(mqttServ, "SessionLocal", Mock(return_value=mock_db))
    monkeypatch.setattr(mqttServ.data_repository, "queryProcesarMensajeAsig2", Mock(return_value=None))
    mock_crear_tanque = Mock()
    monkeypatch.setattr(mqttServ.telemetria_service, "crear_telemetria_tanque", mock_crear_tanque)

    msg = NS(
        topic=mqttServ.MQTT_TOPIC_CONTROL_AGUA,
        payload=json.dumps({
            "id_asignacion": 9,
            "distancia_cm": 25.0,
            "estado_bomba": "OFF",
        }).encode("utf-8"),
    )

    with caplog.at_level(logging.DEBUG):
        mqttServ.procesar_mensajeServ(Mock(), None, msg)

    mock_crear_tanque.assert_not_called()
    mock_db.close.assert_called_once()

    warnings_or_errors = [
        record for record in caplog.records
        if record.levelno >= logging.INFO
    ]
    assert warnings_or_errors == []

    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("Asignación con id 9 no encontrada para telemetría de tanque" in m for m in debug_msgs)


def test_procesar_mensaje_riego_unassigned_omitted_without_warning(monkeypatch, caplog):
    import logging
    from unittest.mock import MagicMock
    from src.main.service import mqttServ

    mock_db = MagicMock()
    monkeypatch.setattr(mqttServ, "SessionLocal", Mock(return_value=mock_db))
    monkeypatch.setattr(mqttServ.data_repository, "queryProcesarMensajeAsig", Mock(return_value=None))
    mock_crear_riego = Mock()
    monkeypatch.setattr(mqttServ.telemetria_repository, "crear_datos_riego", mock_crear_riego)

    msg = NS(
        topic=mqttServ.MQTT_TOPIC_RIEGO_DATOS,
        payload=json.dumps({
            "humedad_suelo": {"id_asignacion": 9, "valor": 300, "porcentaje": 45.0},
            "humedad_ambiente": {"id_asignacion": 9, "valor": 60, "porcentaje": 60.0},
            "temperatura_ambiente": {"id_asignacion": 9, "valor": 22, "temperatura": 22.0},
            "temperatura_suelo": {"id_asignacion": 9, "valor": 20, "temperatura": 20.0},
        }).encode("utf-8"),
    )

    with caplog.at_level(logging.DEBUG):
        mqttServ.procesar_mensajeServ(Mock(), None, msg)

    mock_crear_riego.assert_not_called()
    mock_db.close.assert_called_once()

    warnings_or_errors = [
        record for record in caplog.records
        if record.levelno >= logging.INFO
    ]
    assert warnings_or_errors == []

    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("Asignación con id 9 no encontrada para telemetría de riego" in m for m in debug_msgs)
