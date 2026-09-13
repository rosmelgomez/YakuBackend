import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, MagicMock
import pytest
from fastapi import HTTPException

from src.main.service import dispositivoServ
from src.main.service import mlServ
from src.main.service import mqttServ


def test_deactivating_actuator_stops_irrigation_and_clears_pump(monkeypatch):
    device = NS(id_dispositivo=2, client_id_mqtt="ESP32_ACT_01", id_tipo=2, estado="activo", tipo=NS(nombre="Actuador"))
    assignment = NS(id=10, id_usuario=1, id_cultivo=5, id_dispositivo=2, activo=True)
    tank_config = NS(id_asignacion=10, bomba_encendida=True, valvula_abierta=True)

    monkeypatch.setattr(dispositivoServ, "sync_device_health", Mock())
    monkeypatch.setattr(dispositivoServ.data_repository, "queryActualizarFuncionamientoUsuarioDispositivo", Mock(return_value=device))
    monkeypatch.setattr(dispositivoServ.data_repository, "queryActualizarFuncionamientoUsuarioAsigQuery", Mock())
    monkeypatch.setattr(dispositivoServ.data_repository, "queryActualizarFuncionamientoUsuarioAsigs", Mock(return_value=[assignment]))
    monkeypatch.setattr(dispositivoServ.data_repository, "queryConfiguracionTanquePorAsignacion", Mock(return_value=tank_config))

    mock_stop_irrigation = Mock()
    monkeypatch.setattr("src.main.service.irrigationServ.stop_irrigation", mock_stop_irrigation)
    monkeypatch.setattr(dispositivoServ, "publish_mqtt_message", Mock())

    mock_db = MagicMock()
    current_user = NS(id_usuario=1, id_rol=2)

    dispositivoServ.actualizar_funcionamiento_usuario(2, False, mock_db, current_user)

    assert assignment.activo is False
    assert tank_config.bomba_encendida is False
    assert tank_config.valvula_abierta is False
    mock_stop_irrigation.assert_called_once_with(mock_db, assignment, "dispositivo_desactivado", publish=True)


def test_live_ml_check_rejected_when_irrigation_is_in_progress(monkeypatch):
    assignment = NS(id=10, id_usuario=1, id_cultivo=5, activo=True)
    tank_config = NS(id_asignacion=10, bomba_encendida=True)

    monkeypatch.setattr("src.main.service.irrigationServ.find_pump_assignment", Mock(return_value=assignment))
    monkeypatch.setattr("src.main.repositories.controlRep.queryObtenerDatosControlSesionActiva", Mock(return_value=NS(id=99)))
    monkeypatch.setattr("src.main.repositories.controlRep.queryObtenerDatosControlConfigT", Mock(return_value=tank_config))

    mock_db = MagicMock()
    current_user = NS(id_usuario=1, id_rol=2)

    with pytest.raises(HTTPException) as exc_info:
        mlServ.ejecutar_prediccion_en_vivoServ(5, db=mock_db, current_user=current_user)

    assert exc_info.value.status_code == 400
    assert "en ejecución" in exc_info.value.detail


def test_live_ml_check_rejected_when_actuator_is_inactive(monkeypatch):
    assignment = NS(id=10, id_usuario=1, id_cultivo=5, activo=False)

    monkeypatch.setattr("src.main.service.irrigationServ.find_pump_assignment", Mock(return_value=assignment))

    mock_db = MagicMock()
    current_user = NS(id_usuario=1, id_rol=2)

    with pytest.raises(HTTPException) as exc_info:
        mlServ.ejecutar_prediccion_en_vivoServ(5, db=mock_db, current_user=current_user)

    assert exc_info.value.status_code == 400
    assert "apagado" in exc_info.value.detail


def test_mqtt_telemetry_skips_ml_when_actuator_is_inactive(monkeypatch):
    mock_db = MagicMock()
    monkeypatch.setattr(mqttServ, "SessionLocal", Mock(return_value=mock_db))

    sensor_asig = NS(id=1, id_usuario=1, id_cultivo=5, activo=True, dispositivo=NS(id_usuario=1, id_dispositivo=1))
    monkeypatch.setattr(mqttServ.data_repository, "queryProcesarMensajeAsig", Mock(return_value=sensor_asig))
    monkeypatch.setattr(mqttServ.telemetria_repository, "crear_datos_riego", Mock())
    monkeypatch.setattr("src.main.service.deviceHealthServ.touch_device_by_assignment", Mock())
    monkeypatch.setattr(mqttServ.data_repository, "queryProcesarMensajeUsrMod", Mock(return_value=NS(activo=True, id_modelo=1)))

    # Actuador inactivo
    pump_asig = NS(id=10, activo=False)
    monkeypatch.setattr("src.main.service.irrigationServ.find_pump_assignment", Mock(return_value=pump_asig))

    mock_ml = Mock()
    monkeypatch.setattr(mqttServ, "obtener_prediccion_riego", mock_ml)

    msg = NS(
        topic=mqttServ.MQTT_TOPIC_RIEGO_DATOS,
        payload=json.dumps({
            "id_asignacion": 1,
            "humedad_suelo": {"valor": 20, "id_asignacion": 1, "porcentaje": 20},
            "humedad_ambiente": {"valor": 50, "id_asignacion": 1, "porcentaje": 50},
            "temperatura_ambiente": {"temperatura": 24, "id_asignacion": 1},
            "temperatura_suelo": {"temperatura": 22, "id_asignacion": 1},
        }).encode("utf-8"),
    )

    mqttServ.procesar_mensajeServ(Mock(), None, msg)
    mock_ml.assert_not_called()


def test_mqtt_telemetry_skips_ml_when_irrigation_is_in_progress(monkeypatch):
    mock_db = MagicMock()
    monkeypatch.setattr(mqttServ, "SessionLocal", Mock(return_value=mock_db))

    sensor_asig = NS(id=1, id_usuario=1, id_cultivo=5, activo=True, dispositivo=NS(id_usuario=1, id_dispositivo=1))
    monkeypatch.setattr(mqttServ.data_repository, "queryProcesarMensajeAsig", Mock(return_value=sensor_asig))
    monkeypatch.setattr(mqttServ.telemetria_repository, "crear_datos_riego", Mock())
    monkeypatch.setattr("src.main.service.deviceHealthServ.touch_device_by_assignment", Mock())
    monkeypatch.setattr(mqttServ.data_repository, "queryProcesarMensajeUsrMod", Mock(return_value=NS(activo=True, id_modelo=1)))

    # Actuador activo pero con riego en curso
    pump_asig = NS(id=10, activo=True)
    monkeypatch.setattr("src.main.service.irrigationServ.find_pump_assignment", Mock(return_value=pump_asig))
    monkeypatch.setattr("src.main.repositories.controlRep.queryObtenerDatosControlSesionActiva", Mock(return_value=NS(id=88)))
    monkeypatch.setattr("src.main.repositories.controlRep.queryObtenerDatosControlConfigT", Mock(return_value=NS(bomba_encendida=True)))

    mock_ml = Mock()
    monkeypatch.setattr(mqttServ, "obtener_prediccion_riego", mock_ml)

    msg = NS(
        topic=mqttServ.MQTT_TOPIC_RIEGO_DATOS,
        payload=json.dumps({
            "id_asignacion": 1,
            "humedad_suelo": {"valor": 20, "id_asignacion": 1, "porcentaje": 20},
            "humedad_ambiente": {"valor": 50, "id_asignacion": 1, "porcentaje": 50},
            "temperatura_ambiente": {"temperatura": 24, "id_asignacion": 1},
            "temperatura_suelo": {"temperatura": 22, "id_asignacion": 1},
        }).encode("utf-8"),
    )

    mqttServ.procesar_mensajeServ(Mock(), None, msg)
    mock_ml.assert_not_called()
