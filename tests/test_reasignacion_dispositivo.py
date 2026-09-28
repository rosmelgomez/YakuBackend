"""Reasignar un dispositivo a otro agricultor: la telemetria debe llegar al nuevo.

El ESP32 guarda en NVS los ids de asignacion y solo los pide al conectarse.
Tras liberar -> reasignar -> activar, el backend debe enviarle los ids del
nuevo titular, y las lecturas que aun lleguen con ids del anterior no deben
quedar guardadas en el historial de ese agricultor.
"""

import json
from types import SimpleNamespace

import pytest

from src.main.core.mqttConfig import MQTT_TOPIC_RIEGO_DATOS
from src.main.model.models import (
    asignaciones_iot,
    cultivos,
    humedad_suelo,
    tipos_dispositivo,
    usuarios,
)
from src.main.service import deviceConfigServ, dispositivoServ, mqttServ, usuarioServ
from test_mqtt_ingesta import _escenario_base, _mensaje, _metrica, _payload_sensores, _procesar

ADMIN = SimpleNamespace(id_rol=1, id_usuario=None, correo="admin@yaku.test")
METRICAS = {"hs": "HUM_SUELO", "ha": "HUM_AMB", "ta": "TEMP_AMB", "ts": "TEMP_SUELO"}


@pytest.fixture(autouse=True)
def _sin_throttle():
    mqttServ._ultimo_reenvio_config.clear()


def _colector(db):
    """Escenario base con un tipo de colector de sensores (id fijo, lejos de 1 y 2:
    deviceHealthServ trata id_tipo 2 como actuador)."""
    usuario, fuente, cultivo, disp = _escenario_base(db)
    tipo = db.get(tipos_dispositivo, 9001)
    if tipo is None:
        tipo = tipos_dispositivo(id=9001, nombre="Colector de sensores")
        db.add(tipo)
        db.flush()
    disp.id_tipo = tipo.id
    db.commit()
    return usuario, fuente, cultivo, disp


def _nuevo_agricultor(db, fuente_de):
    n = db.query(usuarios).count() + 1000
    usuario = usuarios(nombre="Nuevo", correo=f"nuevo{n}@yaku.test", contrasena="x")
    db.add(usuario)
    db.flush()
    cultivo = cultivos(
        id_usuario=usuario.id_usuario, nombre_planta="Tomate", id_fuente_agua=fuente_de.id
    )
    db.add(cultivo)
    db.commit()
    return usuario, cultivo


def _asignar_con_sensores(db, disp, usuario, cultivo):
    """Asignar el equipo (fila base) y vincular los 4 sensores, como hace el admin."""
    dispositivoServ.asignar_dispositivo_a_cultivoServ(
        disp.id_dispositivo, usuario.id_usuario, cultivo.id_cultivo, db=db, current_user=ADMIN
    )
    asigs = {}
    for clave, codigo in METRICAS.items():
        a = asignaciones_iot(
            id_usuario=usuario.id_usuario,
            id_dispositivo=disp.id_dispositivo,
            id_cultivo=cultivo.id_cultivo,
            id_tipo_metrica=_metrica(db, codigo, "%").id,
            pin_gpio=4,
            activo=False,
        )
        db.add(a)
        db.flush()
        asigs[clave] = a
    db.commit()
    return asigs


def _activar(db, disp):
    dispositivoServ.actualizar_funcionamiento_usuario(disp.id_dispositivo, True, db, ADMIN)


def _ultima_config(publicados, disp):
    topic = f"yaku/dispositivo/{disp.client_id_mqtt}/config"
    payloads = [p for t, p in publicados if t == topic]
    assert payloads, "no se publico ninguna configuracion"
    return json.loads(payloads[-1])


@pytest.fixture()
def reasignado(db, mqtt_publicado):
    """Equipo usado por A, liberado a stock y reasignado y activado para B."""
    usuario_a, fuente, cultivo_a, disp = _colector(db)
    viejas = _asignar_con_sensores(db, disp, usuario_a, cultivo_a)
    _activar(db, disp)
    dispositivoServ.liberar_dispositivo_a_stockServ(disp.id_dispositivo, db=db, current_user=ADMIN)

    usuario_b, cultivo_b = _nuevo_agricultor(db, fuente)
    nuevas = _asignar_con_sensores(db, disp, usuario_b, cultivo_b)
    _activar(db, disp)
    return SimpleNamespace(
        disp=disp, a=usuario_a, b=usuario_b, cultivo_b=cultivo_b, viejas=viejas, nuevas=nuevas
    )


def test_al_activar_se_envian_los_ids_del_nuevo_titular(db, reasignado, mqtt_publicado):
    config = _ultima_config(mqtt_publicado, reasignado.disp)
    assert config["funcionamiento_activo"] is True
    for clave, codigo in METRICAS.items():
        assert config["asignaciones"][codigo] == reasignado.nuevas[clave].id


def test_activar_no_reactiva_las_asignaciones_del_titular_anterior(db, reasignado):
    db.expire_all()
    assert not any(a.activo for a in reasignado.viejas.values())
    assert all(a.activo for a in reasignado.nuevas.values())
    assert reasignado.disp.id_usuario == reasignado.b.id_usuario


def test_telemetria_con_ids_viejos_se_descarta_y_se_reenvia_config(
    db, reasignado, mqtt_publicado
):
    publicados_antes = len(mqtt_publicado)
    _procesar(MQTT_TOPIC_RIEGO_DATOS, _payload_sensores(reasignado.viejas))

    db.expire_all()
    viejas_ids = [a.id for a in reasignado.viejas.values()]
    assert db.query(humedad_suelo).filter(humedad_suelo.id_asignacion.in_(viejas_ids)).count() == 0
    # Se le reenvio al equipo la configuracion con los ids de B
    assert len(mqtt_publicado) == publicados_antes + 1
    config = _ultima_config(mqtt_publicado, reasignado.disp)
    assert config["asignaciones"]["HUM_SUELO"] == reasignado.nuevas["hs"].id


def test_reenvio_de_config_limitado_por_dispositivo(db, reasignado, mqtt_publicado):
    publicados_antes = len(mqtt_publicado)
    for _ in range(3):
        _procesar(MQTT_TOPIC_RIEGO_DATOS, _payload_sensores(reasignado.viejas))
    assert len(mqtt_publicado) == publicados_antes + 1


def test_telemetria_con_ids_nuevos_llega_al_nuevo_agricultor(
    db, reasignado, _aislar_efectos_secundarios
):
    _procesar(MQTT_TOPIC_RIEGO_DATOS, _payload_sensores(reasignado.nuevas))

    db.expire_all()
    assert db.query(humedad_suelo).filter_by(id_asignacion=reasignado.nuevas["hs"].id).count() == 1
    destinatarios = {uid for _, uid in _aislar_efectos_secundarios}
    assert destinatarios == {reasignado.b.id_usuario}


def test_config_req_responde_con_el_titular_actual(db, reasignado):
    publicados = []
    cliente = SimpleNamespace(publish=lambda topic, payload, **k: publicados.append((topic, payload)))
    # El equipo pide config enviando todavia un id viejo
    msg = _mensaje(
        f"yaku/dispositivo/{reasignado.disp.client_id_mqtt}/config/req",
        {"client_id": reasignado.disp.client_id_mqtt, "id_asignacion": reasignado.viejas["hs"].id},
    )
    mqttServ.procesar_mensajeServ(client=cliente, userdata=None, msg=msg)

    config = json.loads(publicados[-1][1])
    assert config["asignaciones"]["HUM_SUELO"] == reasignado.nuevas["hs"].id
    assert config["funcionamiento_activo"] is True


def test_liberar_apaga_y_borra_los_ids_del_equipo(db, mqtt_publicado):
    usuario, _, cultivo, disp = _colector(db)
    _asignar_con_sensores(db, disp, usuario, cultivo)
    _activar(db, disp)
    dispositivoServ.liberar_dispositivo_a_stockServ(disp.id_dispositivo, db=db, current_user=ADMIN)

    config = _ultima_config(mqtt_publicado, disp)
    assert config["funcionamiento_activo"] is False
    assert set(config["asignaciones"].values()) == {0}


def test_baja_de_usuario_y_reasignacion_no_mezcla_ids(db, mqtt_publicado):
    """La baja no limpia las metricas de las filas viejas: no deben competir con las nuevas."""
    usuario_a, fuente, cultivo_a, disp = _colector(db)
    _asignar_con_sensores(db, disp, usuario_a, cultivo_a)
    _activar(db, disp)
    usuarioServ.cambiar_estado_usuarioServ(
        usuario_a.id_usuario, False, db=db, current_user=SimpleNamespace(id_rol=1, id_usuario=None, correo="admin@yaku.test")
    )

    usuario_b, cultivo_b = _nuevo_agricultor(db, fuente)
    nuevas = _asignar_con_sensores(db, disp, usuario_b, cultivo_b)
    _activar(db, disp)

    config = _ultima_config(mqtt_publicado, disp)
    for clave, codigo in METRICAS.items():
        assert config["asignaciones"][codigo] == nuevas[clave].id


def test_flujometro_recibe_id_asignacion_en_la_raiz(db):
    usuario, fuente, cultivo, disp = _escenario_base(
        db, metodo_medicion="flujometro", tipo_fuente="conexion_directa"
    )
    disp.estado = "asignado"
    caudal = asignaciones_iot(
        id_usuario=usuario.id_usuario,
        id_dispositivo=disp.id_dispositivo,
        id_cultivo=cultivo.id_cultivo,
        id_tipo_metrica=_metrica(db, "CAUDAL", "L/min").id,
        activo=True,
    )
    db.add(caudal)
    db.commit()

    config = deviceConfigServ.construir_config_dispositivo(db, disp)
    assert config["id_asignacion"] == caudal.id
    assert config["asignaciones"]["CAUDAL"] == caudal.id


def test_componentes_ocupan_la_fila_base_sin_asignacion_de_mas(db):
    """Asignar el equipo crea una fila base; al vincular N componentes deben quedar
    N filas (la primera reutiliza la base), no N + 1."""
    import uuid

    from src.main.dtos.dispositivoDto import AsignarComponentePayload
    from src.main.model.models import componentes, tipos_componente

    usuario, _fuente, cultivo, disp = _colector(db)
    dispositivoServ.asignar_dispositivo_a_cultivoServ(
        disp.id_dispositivo, usuario.id_usuario, cultivo.id_cultivo, db=db, current_user=ADMIN
    )
    filas = lambda: (
        db.query(asignaciones_iot)
        .filter(asignaciones_iot.id_dispositivo == disp.id_dispositivo,
                asignaciones_iot.id_usuario == usuario.id_usuario)
        .order_by(asignaciones_iot.id)
        .all()
    )
    base_id = filas()[0].id

    for pin, codigo in zip((17, 15, 16), ("HUM_SUELO", "TEMP_AMB", "TEMP_SUELO")):
        metrica = _metrica(db, codigo, "%")
        tipo = tipos_componente(nombre_modelo=f"Sensor {uuid.uuid4().hex[:8]}", categoria="sensor")
        db.add(tipo)
        db.flush()
        comp = componentes(id_tipo_componente=tipo.id, numero_serie=uuid.uuid4().hex[:12])
        db.add(comp)
        db.commit()
        dispositivoServ.asignar_componente_dispositivoServ(
            AsignarComponentePayload(id_dispositivo=disp.id_dispositivo, id_componente=comp.id,
                                     pin_gpio=pin, id_tipo_metrica=metrica.id),
            db=db, current_user=ADMIN,
        )

    resultado = filas()
    assert len(resultado) == 3
    assert resultado[0].id == base_id
    assert all(f.id_componente is not None and f.id_tipo_metrica is not None for f in resultado)
    assert all(f.id_cultivo == cultivo.id_cultivo for f in resultado)


def test_reiniciar_backend_no_modifica_las_asignaciones(db):
    """run_migrations() corre en cada arranque: no debe vaciar ni borrar las
    asignaciones de un dispositivo cuyo primer componente ocupó la fila base."""
    from src.main.repositories import bootstrapRep

    usuario, _fuente, cultivo, disp = _colector(db)
    dispositivoServ.asignar_dispositivo_a_cultivoServ(
        disp.id_dispositivo, usuario.id_usuario, cultivo.id_cultivo, db=db, current_user=ADMIN
    )
    import uuid

    from src.main.model.models import componentes, tipos_componente

    def _componente():
        tipo = tipos_componente(nombre_modelo=f"Sensor {uuid.uuid4().hex[:8]}", categoria="sensor")
        db.add(tipo)
        db.flush()
        comp = componentes(id_tipo_componente=tipo.id, numero_serie=uuid.uuid4().hex[:12], estado="asignado")
        db.add(comp)
        db.flush()
        return comp.id

    # Como queda tras vincular 2 componentes: la fila base ocupada por el primero.
    base = db.query(asignaciones_iot).filter_by(id_dispositivo=disp.id_dispositivo).one()
    base.id_componente = _componente()
    base.id_tipo_metrica = _metrica(db, "HUM_SUELO", "%").id
    base.pin_gpio = 17
    otra = asignaciones_iot(id_usuario=usuario.id_usuario, id_dispositivo=disp.id_dispositivo,
                            id_cultivo=cultivo.id_cultivo, id_componente=_componente(),
                            id_tipo_metrica=_metrica(db, "TEMP_SUELO", "C").id,
                            pin_gpio=16, activo=False)
    db.add(otra)
    db.commit()

    def estado():
        db.expire_all()
        return [(a.id, a.id_componente, a.id_tipo_metrica, a.pin_gpio)
                for a in db.query(asignaciones_iot).filter_by(id_dispositivo=disp.id_dispositivo).order_by(asignaciones_iot.id)]

    antes = estado()
    db.rollback()  # suelta el lock de lectura: las migraciones hacen ALTER TABLE
    bootstrapRep.run_migrations()
    bootstrapRep.run_migrations()
    assert estado() == antes
