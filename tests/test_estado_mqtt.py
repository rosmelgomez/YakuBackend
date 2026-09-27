"""Estado de la conexión MQTT del backend, visible para el administrador.

Se usa el cliente paho real contra un broker falso local (un socket que
responde CONNACK con el código elegido): nunca se contacta un broker real.
"""

import socket
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import src.main.tasks.mqttSubscriberTask as mqtt_task
from src.main.service import mqttConfigServ

# Referencias reales: conftest reemplaza start_mqtt para prohibir el broker real.
_start_mqtt_real = mqtt_task.start_mqtt
_stop_mqtt_real = mqtt_task.stop_mqtt

ADMIN = SimpleNamespace(id_rol=1, id_usuario=1)


class BrokerFalso:
    """Acepta conexiones y responde CONNACK (MQTT 3.1.1) con `codigo`."""

    def __init__(self, codigo: int):
        self.codigo = codigo
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.activo = True
        self.conexiones = []
        threading.Thread(target=self._servir, daemon=True).start()

    def _servir(self):
        while self.activo:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            self.conexiones.append(conn)
            try:
                conn.recv(1024)  # paquete CONNECT
                conn.sendall(bytes([0x20, 0x02, 0x00, self.codigo]))
            except OSError:
                pass

    def cerrar(self):
        self.activo = False
        for conn in self.conexiones:
            conn.close()
        self.sock.close()


@pytest.fixture()
def cliente_mqtt(monkeypatch):
    """Arranca el cliente real con la config dada y lo detiene al final."""
    monkeypatch.setattr(mqtt_task, "_current_config", dict(mqtt_task._current_config))
    monkeypatch.setattr(mqtt_task, "_mqtt_client", None)
    brokers = []

    def arrancar(port: int, username="yaku-backend", password="clave-test-1", broker=None):
        if broker:
            brokers.append(broker)
        return _start_mqtt_real({
            "host": "127.0.0.1", "port": port, "username": username,
            "password": password, "tls_enabled": False,
        })

    yield arrancar
    _stop_mqtt_real()
    for broker in brokers:
        broker.cerrar()


def _esperar_estado(*estados, timeout=8.0):
    fin = time.time() + timeout
    while time.time() < fin:
        estado = mqtt_task.obtener_estado_mqtt()
        if estado["estado"] in estados:
            return estado
        time.sleep(0.05)
    raise AssertionError(f"Estado final: {mqtt_task.obtener_estado_mqtt()}")


def test_credenciales_correctas_quedan_conectado(cliente_mqtt):
    broker = BrokerFalso(codigo=0)
    cliente_mqtt(broker.port, broker=broker)

    estado = _esperar_estado("conectado", "error")

    assert estado["estado"] == "conectado"
    assert estado["host"] == "127.0.0.1"
    assert estado["username"] == "yaku-backend"
    assert "password" not in estado
    assert estado["desde"] is not None


@pytest.mark.parametrize(
    "codigo, texto",
    [(5, "No autorizado"), (4, "Usuario o contraseña incorrectos")],
)
def test_credenciales_rechazadas_muestran_el_motivo(cliente_mqtt, codigo, texto):
    broker = BrokerFalso(codigo=codigo)
    cliente_mqtt(broker.port, broker=broker)

    estado = _esperar_estado("error")

    assert estado["codigo"] == codigo
    assert texto in estado["mensaje"]
    # La desconexión posterior al rechazo no reemplaza el motivo.
    time.sleep(0.3)
    assert mqtt_task.obtener_estado_mqtt()["codigo"] == codigo


def test_broker_inalcanzable_queda_en_error(cliente_mqtt):
    libre = socket.socket()
    libre.bind(("127.0.0.1", 0))
    port = libre.getsockname()[1]
    libre.close()  # puerto cerrado: nadie escucha

    cliente_mqtt(port)

    estado = _esperar_estado("error")
    assert "No se pudo abrir la conexión" in estado["mensaje"]


def test_reconectar_con_credenciales_corregidas_vuelve_a_conectado(cliente_mqtt):
    malo = BrokerFalso(codigo=5)
    cliente_mqtt(malo.port, password="clave-mala", broker=malo)
    _esperar_estado("error")

    bueno = BrokerFalso(codigo=0)
    _stop_mqtt_real()
    cliente_mqtt(bueno.port, password="clave-buena", broker=bueno)

    assert _esperar_estado("conectado", "error")["estado"] == "conectado"


def test_estado_solo_para_administradores():
    with pytest.raises(HTTPException) as exc:
        mqttConfigServ.obtener_estado_mqttServ(SimpleNamespace(id_rol=2, id_usuario=5))
    assert exc.value.status_code == 403
    assert "estado" in mqttConfigServ.obtener_estado_mqttServ(ADMIN)
