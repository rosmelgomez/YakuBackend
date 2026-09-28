"""Integración: mensajes MQTT de sensores y actuadores llegan a PostgreSQL.

Se invoca el mismo handler que usa el suscriptor (mqttServ.procesar_mensajeServ)
con mensajes MQTT construidos a mano, y se verifica lo que quedó en la base.
"""

import json
from datetime import datetime
from decimal import Decimal
from itertools import count

import paho.mqtt.client as mqtt
import pytest

from src.main.core.mqttConfig import MQTT_TOPIC_CONTROL_AGUA, MQTT_TOPIC_RIEGO_DATOS
from src.main.model.models import (
    asignaciones_iot,
    configuracion_actuador,
    cultivos,
    dispositivos,
    fuentes_agua,
    humedad_ambiente,
    humedad_suelo,
    riego,
    telemetria_tanque,
    temperatura_ambiente,
    temperatura_suelo,
    tipos_dispositivo,
    tipos_metrica,
    usuarios,
)
from src.main.service import mqttServ

_seq = count(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mensaje(topic: str, payload) -> mqtt.MQTTMessage:
    msg = mqtt.MQTTMessage(topic=topic.encode())
    msg.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return msg


def _procesar(topic: str, payload) -> None:
    mqttServ.procesar_mensajeServ(client=None, userdata=None, msg=_mensaje(topic, payload))


def _metrica(db, codigo, unidad):
    m = db.query(tipos_metrica).filter_by(codigo=codigo).first()
    if m is None:
        m = tipos_metrica(codigo=codigo, nombre=codigo, unidad=unidad)
        db.add(m)
        db.flush()
    return m


def _escenario_base(db, metodo_medicion=None, tipo_fuente="tanque"):
    n = next(_seq)
    usuario = usuarios(nombre="Test", correo=f"test{n}@yaku.test", contrasena="x")
    db.add(usuario)
    db.flush()
    # ck_fuentes_agua_config: solo el tanque lleva capacidad y alturas.
    dimensiones = (
        {"capacidad_litros": 100, "altura_tanque_cm": 100, "altura_seguridad_cm": 10}
        if tipo_fuente == "tanque"
        else {}
    )
    fuente = fuentes_agua(
        id_usuario=usuario.id_usuario, nombre=f"Fuente {n}", tipo=tipo_fuente, **dimensiones
    )
    db.add(fuente)
    db.flush()
    cultivo = cultivos(
        id_usuario=usuario.id_usuario, nombre_planta="Lechuga", id_fuente_agua=fuente.id
    )
    tipo = tipos_dispositivo(nombre=f"Tipo {n}", metodo_medicion=metodo_medicion)
    db.add_all([cultivo, tipo])
    db.flush()
    disp = dispositivos(
        id_tipo=tipo.id,
        nombre=f"ESP32 {n}",
        client_id_mqtt=f"ESP32_TEST_{n}",
        mac_address=f"AA:BB:CC:00:00:{n:02X}",
    )
    db.add(disp)
    db.flush()
    return usuario, fuente, cultivo, disp


def _asignacion(db, usuario, cultivo, disp, metrica=None, fuente=None, offset=0, activo=True):
    a = asignaciones_iot(
        id_usuario=usuario.id_usuario,
        id_dispositivo=disp.id_dispositivo,
        id_cultivo=cultivo.id_cultivo,
        id_tipo_metrica=metrica.id if metrica else None,
        id_fuente_agua=fuente.id if fuente else None,
        pin_gpio=4,
        activo=activo,
        offset_calibracion=offset,
    )
    db.add(a)
    db.flush()
    return a


@pytest.fixture()
def colector(db):
    """Dispositivo colector con sus 4 asignaciones de sensores."""
    usuario, _, cultivo, disp = _escenario_base(db)
    asigs = {
        "hs": _asignacion(db, usuario, cultivo, disp, _metrica(db, "HUM_SUELO", "%")),
        "ha": _asignacion(db, usuario, cultivo, disp, _metrica(db, "HUM_AMB", "%")),
        "ta": _asignacion(db, usuario, cultivo, disp, _metrica(db, "TEMP_AMB", "°C")),
        "ts": _asignacion(db, usuario, cultivo, disp, _metrica(db, "TEMP_SUELO", "°C")),
    }
    db.commit()
    return {"usuario": usuario, "cultivo": cultivo, "disp": disp, **asigs}


def _payload_sensores(c, **overrides):
    payload = {
        "humedad_suelo": {"id_asignacion": c["hs"].id, "valor": 2100, "porcentaje": 45.5, "ema": 45.2, "desviacion": 0.4},
        "humedad_ambiente": {"id_asignacion": c["ha"].id, "valor": 61.3, "porcentaje": 61.3, "ema": 61.0},
        "temperatura_ambiente": {"id_asignacion": c["ta"].id, "valor": 23.4, "temperatura": 23.4, "ema": 23.1},
        "temperatura_suelo": {"id_asignacion": c["ts"].id, "valor": 19.8, "temperatura": 19.8, "ema": 19.7},
    }
    for clave, valores in overrides.items():
        payload[clave].update(valores)
    return payload


def _unica(db, modelo, id_asignacion):
    db.expire_all()
    filas = db.query(modelo).filter_by(id_asignacion=id_asignacion).all()
    assert len(filas) == 1, f"{modelo.__tablename__}: se esperaba 1 fila, hay {len(filas)}"
    return filas[0]


# ---------------------------------------------------------------------------
# Sensores (yaku/riego/datos)
# ---------------------------------------------------------------------------


def test_sensores_se_guardan_en_sus_cuatro_tablas(db, colector, _aislar_efectos_secundarios):
    _procesar(MQTT_TOPIC_RIEGO_DATOS, _payload_sensores(colector))

    hs = _unica(db, humedad_suelo, colector["hs"].id)
    assert hs.valor == Decimal("2100.00")
    assert hs.porcentaje == Decimal("45.50")
    assert hs.ema == Decimal("45.20")
    assert hs.desviacion == Decimal("0.400")
    assert hs.valido is True
    assert hs.fecha is not None

    ha = _unica(db, humedad_ambiente, colector["ha"].id)
    assert ha.porcentaje == Decimal("61.30")

    ta = _unica(db, temperatura_ambiente, colector["ta"].id)
    assert ta.temperatura == Decimal("23.40")

    ts = _unica(db, temperatura_suelo, colector["ts"].id)
    assert ts.temperatura == Decimal("19.80")

    # Se marca el dispositivo como vivo y se notifica al dashboard.
    disp = db.get(dispositivos, colector["disp"].id_dispositivo)
    assert disp.ultimo_ping is not None
    eventos = _aislar_efectos_secundarios
    assert len(eventos) == 1
    evento, uid = eventos[0]
    assert uid == colector["usuario"].id_usuario
    assert evento["event"] == "telemetria"
    assert set(evento["lecturas"]) == {"humedadSuelo", "humedadAmbiente", "temperaturaAmbiente", "temperaturaSuelo"}


def test_sensores_aplican_offset_de_calibracion(db):
    usuario, _, cultivo, disp = _escenario_base(db)
    c = {
        "hs": _asignacion(db, usuario, cultivo, disp, _metrica(db, "HUM_SUELO", "%"), offset=5),
        "ha": _asignacion(db, usuario, cultivo, disp, _metrica(db, "HUM_AMB", "%")),
        "ta": _asignacion(db, usuario, cultivo, disp, _metrica(db, "TEMP_AMB", "°C"), offset=-1.5),
        "ts": _asignacion(db, usuario, cultivo, disp, _metrica(db, "TEMP_SUELO", "°C")),
    }
    db.commit()

    _procesar(MQTT_TOPIC_RIEGO_DATOS, _payload_sensores(c))

    hs = _unica(db, humedad_suelo, c["hs"].id)
    assert hs.porcentaje == Decimal("50.50")
    assert hs.ema == Decimal("50.20")
    ta = _unica(db, temperatura_ambiente, c["ta"].id)
    assert ta.temperatura == Decimal("21.90")
    assert ta.ema == Decimal("21.60")
    # Sin offset: sin cambios.
    assert _unica(db, humedad_ambiente, c["ha"].id).porcentaje == Decimal("61.30")


def test_sensores_guardan_lecturas_validas_aunque_una_asignacion_no_exista(db, colector):
    payload = _payload_sensores(colector, humedad_suelo={"id_asignacion": 0})

    _procesar(MQTT_TOPIC_RIEGO_DATOS, payload)

    db.expire_all()
    assert db.query(humedad_suelo).filter_by(id_asignacion=0).count() == 0
    _unica(db, humedad_ambiente, colector["ha"].id)
    _unica(db, temperatura_ambiente, colector["ta"].id)
    _unica(db, temperatura_suelo, colector["ts"].id)


def test_sensores_con_asignaciones_inexistentes_se_descartan(db, colector):
    antes = db.query(humedad_suelo).count()
    payload = {k: {"id_asignacion": 999_999, "valor": 1} for k in
               ("humedad_suelo", "humedad_ambiente", "temperatura_ambiente", "temperatura_suelo")}

    _procesar(MQTT_TOPIC_RIEGO_DATOS, payload)

    db.expire_all()
    assert db.query(humedad_suelo).count() == antes


@pytest.mark.parametrize(
    "payload",
    [b"{no es json", {"humedad_suelo": {"id_asignacion": 1}}],  # JSON roto / faltan sensores
    ids=["json_invalido", "payload_incompleto"],
)
def test_sensores_payload_invalido_no_guarda_ni_revienta(db, colector, payload):
    antes = db.query(humedad_suelo).count()

    _procesar(MQTT_TOPIC_RIEGO_DATOS, payload)  # no debe lanzar excepción

    db.expire_all()
    assert db.query(humedad_suelo).count() == antes


# ---------------------------------------------------------------------------
# Actuador (yaku/tanque/datos)
# ---------------------------------------------------------------------------


@pytest.fixture()
def actuador_tanque(db):
    usuario, fuente, cultivo, disp = _escenario_base(db, metodo_medicion="proximidad")
    asig = _asignacion(db, usuario, cultivo, disp, fuente=fuente)
    db.add(configuracion_actuador(id_asignacion=asig.id))
    db.commit()
    return asig


@pytest.fixture()
def actuador_flujo(db):
    usuario, fuente, cultivo, disp = _escenario_base(
        db, metodo_medicion="flujometro", tipo_fuente="conexion_directa"
    )
    asig = _asignacion(db, usuario, cultivo, disp, fuente=fuente)
    db.add(configuracion_actuador(id_asignacion=asig.id))
    db.commit()
    return asig


def test_actuador_tanque_guarda_nivel_calculado(db, actuador_tanque, _aislar_efectos_secundarios):
    _procesar(MQTT_TOPIC_CONTROL_AGUA, {
        "id_asignacion": actuador_tanque.id,
        "distancia_cm": 30,
        "estado_bomba": "OFF",
        "valvula_abierta": False,
    })

    t = _unica(db, telemetria_tanque, actuador_tanque.id)
    assert t.metodo_medicion == "proximidad"
    assert t.distancia_cm == Decimal("30.00")
    # Tanque de 100 cm con 30 cm de distancia al agua => 70 cm, 70 %.
    assert t.nivel_agua_cm == Decimal("70.00")
    assert t.porcentaje_nivel == Decimal("70.00")
    assert t.estado_nivel == "optimo"
    assert t.bomba_encendida is False
    assert t.litros_riego is None

    disp = db.get(dispositivos, actuador_tanque.id_dispositivo)
    assert disp.ultimo_ping is not None
    assert any(e["event"] == "tanque" for e, _ in _aislar_efectos_secundarios)


def test_actuador_reporte_tardio_conserva_la_hora_del_equipo(db, actuador_tanque):
    # Firmware con NTP: un reporte que quedó en cola sin conexión llega tarde
    # con la hora UTC en que ocurrió el evento.
    _procesar(MQTT_TOPIC_CONTROL_AGUA, {
        "id_asignacion": actuador_tanque.id,
        "distancia_cm": 30,
        "estado_bomba": "OFF",
        "motivo_cierre": "tiempo_maximo",
        "fecha": "2026-09-26T14:32:10Z",
    })

    t = _unica(db, telemetria_tanque, actuador_tanque.id)
    assert t.fecha == datetime(2026, 9, 26, 14, 32, 10)


def test_actuador_bomba_encendida_actualiza_estado_y_abre_sesion_de_riego(db, actuador_tanque):
    _procesar(MQTT_TOPIC_CONTROL_AGUA, {
        "id_asignacion": actuador_tanque.id,
        "distancia_cm": 85,
        "estado_bomba": "ON",
        "valvula_abierta": True,
    })

    t = _unica(db, telemetria_tanque, actuador_tanque.id)
    assert t.bomba_encendida is True
    assert t.valvula_abierta is True
    assert t.estado_nivel == "critico"  # 15 %

    config = db.get(configuracion_actuador, actuador_tanque.id)
    assert config.bomba_encendida is True
    assert config.valvula_abierta is True

    sesiones = db.query(riego).filter_by(id_asignacion=actuador_tanque.id).all()
    assert len(sesiones) == 1
    assert sesiones[0].fecha_inicio is not None


def test_actuador_flujometro_guarda_litros(db, actuador_flujo):
    _procesar(MQTT_TOPIC_CONTROL_AGUA, {
        "id_asignacion": actuador_flujo.id,
        "metodo_medicion": "flujometro",
        "estado_bomba": "OFF",
        "litros_riego": 3.25,
        "litros_acumulados": 120.5,
        "caudal_l_min": 6.5,
        "pulsos_riego": 1463,
        "pulsos_por_litro": 450,
    })

    t = _unica(db, telemetria_tanque, actuador_flujo.id)
    assert t.metodo_medicion == "flujometro"
    assert t.litros_riego == Decimal("3.2500")
    assert t.litros_acumulados == Decimal("120.5000")
    assert t.caudal_l_min == Decimal("6.5000")
    assert t.pulsos_riego == 1463
    assert t.pulsos_por_litro == Decimal("450.0000")
    assert t.distancia_cm is None
    assert t.estado_nivel == "no_aplica"


def test_actuador_flujometro_sin_litros_se_rechaza(db, actuador_flujo):
    _procesar(MQTT_TOPIC_CONTROL_AGUA, {
        "id_asignacion": actuador_flujo.id,
        "metodo_medicion": "flujometro",
        "estado_bomba": "OFF",
    })

    db.expire_all()
    assert db.query(telemetria_tanque).filter_by(id_asignacion=actuador_flujo.id).count() == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"id_asignacion": 999_999, "distancia_cm": 30, "estado_bomba": "OFF"},  # asignación inexistente
        {"distancia_cm": 30, "estado_bomba": "OFF"},  # falta id_asignacion
        {"id_asignacion": 1, "estado_bomba": "OFF", "litros_riego": -1},  # litros negativos
    ],
    ids=["asignacion_inexistente", "sin_id_asignacion", "litros_negativos"],
)
def test_actuador_payload_invalido_no_guarda(db, actuador_tanque, payload):
    antes = db.query(telemetria_tanque).count()

    _procesar(MQTT_TOPIC_CONTROL_AGUA, payload)

    db.expire_all()
    assert db.query(telemetria_tanque).count() == antes
