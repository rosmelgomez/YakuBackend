"""Credenciales MQTT por dispositivo: registro, cifrado y provisionamiento."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.main.core import secretCipher
from src.main.dtos.mqttDto import CredencialDispositivoGuardar, MqttConfigUpdate
from src.main.model.models import credenciales_mqtt_dispositivo, mqtt_config
from src.main.service import firmwareServ, mqttConfigServ, mqttCredencialServ
from test_mqtt_ingesta import _asignacion, _escenario_base, _metrica


def _admin(usuario):
    return SimpleNamespace(id_rol=1, id_usuario=usuario.id_usuario)


@pytest.fixture()
def equipo(db):
    """Actuador de tanque listo para aprovisionar (asignación NIVEL_AGUA + fuente)."""
    usuario, fuente, cultivo, disp = _escenario_base(db, metodo_medicion="proximidad")
    disp.client_id_mqtt = f"YAKU-TEST-{disp.id_dispositivo}"
    _asignacion(db, usuario, cultivo, disp, _metrica(db, "NIVEL_AGUA", "%"), fuente=fuente)
    db.commit()
    return SimpleNamespace(usuario=usuario, disp=disp, admin=_admin(usuario))


def _guardar(db, equipo, username, password=None):
    return mqttCredencialServ.guardar_credencialServ(
        equipo.disp.id_dispositivo,
        CredencialDispositivoGuardar(username=username, password=password),
        db=db,
        current_user=equipo.admin,
    )


# ---------------------------------------------------------------------------
# Cifrado
# ---------------------------------------------------------------------------


def test_cifrado_es_reversible_y_no_deja_la_clave_en_claro():
    token = secretCipher.cifrar("clave-super-secreta")
    assert token.startswith("enc:v1:")
    assert "clave-super-secreta" not in token
    assert secretCipher.descifrar(token) == "clave-super-secreta"


def test_valor_previo_al_cifrado_se_lee_tal_cual():
    assert secretCipher.descifrar("clave-antigua-en-claro") == "clave-antigua-en-claro"


def test_sin_clave_de_cifrado_falla_con_mensaje_claro(monkeypatch):
    token = secretCipher.cifrar("x" * 10)
    monkeypatch.delenv("CREDENTIALS_ENCRYPTION_KEY")
    with pytest.raises(secretCipher.SecretoNoDisponible, match="CREDENTIALS_ENCRYPTION_KEY"):
        secretCipher.descifrar(token)


# ---------------------------------------------------------------------------
# Registro y modificación
# ---------------------------------------------------------------------------


def test_registrar_credencial_la_guarda_cifrada(db, equipo):
    resp = _guardar(db, equipo, f"dev-{equipo.disp.id_dispositivo}", "clave-del-equipo-1")

    assert resp["tiene_credencial"] is True
    assert resp["username"] == f"dev-{equipo.disp.id_dispositivo}"
    assert "password" not in resp

    db.expire_all()
    fila = db.query(credenciales_mqtt_dispositivo).filter_by(
        id_dispositivo=equipo.disp.id_dispositivo
    ).one()
    assert fila.password_cifrada.startswith("enc:v1:")
    assert "clave-del-equipo-1" not in fila.password_cifrada
    assert fila.actualizado_por == equipo.usuario.id_usuario


def test_registrar_sin_contrasena_se_rechaza(db, equipo):
    with pytest.raises(HTTPException) as exc:
        _guardar(db, equipo, f"dev-{equipo.disp.id_dispositivo}")
    assert exc.value.status_code == 422


def test_modificar_sin_contrasena_conserva_la_anterior(db, equipo):
    _guardar(db, equipo, f"dev-{equipo.disp.id_dispositivo}", "clave-original-1")

    _guardar(db, equipo, f"dev-{equipo.disp.id_dispositivo}-b")

    cred = mqttCredencialServ.credencial_para_provisionamiento(db, equipo.disp.id_dispositivo)
    assert cred == {"username": f"dev-{equipo.disp.id_dispositivo}-b", "password": "clave-original-1"}


def test_usuario_mqtt_no_puede_repetirse_entre_dispositivos(db, equipo):
    _guardar(db, equipo, f"compartido-{equipo.disp.id_dispositivo}", "clave-original-1")
    usuario, _, _, otro = _escenario_base(db)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        mqttCredencialServ.guardar_credencialServ(
            otro.id_dispositivo,
            CredencialDispositivoGuardar(
                username=f"compartido-{equipo.disp.id_dispositivo}", password="otra-clave-1"
            ),
            db=db,
            current_user=_admin(usuario),
        )
    assert exc.value.status_code == 409


def test_listado_incluye_dispositivos_con_y_sin_credencial(db, equipo):
    usuario, _, _, sin_cred = _escenario_base(db)
    db.commit()
    _guardar(db, equipo, f"dev-{equipo.disp.id_dispositivo}", "clave-del-equipo-1")

    filas = {f["id_dispositivo"]: f for f in mqttCredencialServ.listar_credencialesServ(db, equipo.admin)}

    assert filas[equipo.disp.id_dispositivo]["tiene_credencial"] is True
    assert filas[sin_cred.id_dispositivo]["tiene_credencial"] is False
    assert filas[sin_cred.id_dispositivo]["username"] is None


def test_eliminar_credencial(db, equipo):
    _guardar(db, equipo, f"dev-{equipo.disp.id_dispositivo}", "clave-del-equipo-1")

    mqttCredencialServ.eliminar_credencialServ(equipo.disp.id_dispositivo, db, equipo.admin)

    db.expire_all()
    assert db.query(credenciales_mqtt_dispositivo).filter_by(
        id_dispositivo=equipo.disp.id_dispositivo
    ).count() == 0


def test_solo_administradores(db, equipo):
    agricultor = SimpleNamespace(id_rol=2, id_usuario=equipo.usuario.id_usuario)
    with pytest.raises(HTTPException) as exc:
        mqttCredencialServ.listar_credencialesServ(db, agricultor)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("username", ["con espacio", "comodin/#", "ab"])
def test_usuario_mqtt_invalido(username):
    with pytest.raises(ValueError):
        CredencialDispositivoGuardar(username=username, password="clave-valida-1")


# ---------------------------------------------------------------------------
# Provisionamiento de firmware
# ---------------------------------------------------------------------------


@pytest.fixture()
def broker_panel(db):
    """Broker configurado en el panel (distinto del de .env)."""
    db.query(mqtt_config).delete()
    db.add(mqtt_config(host="broker.panel.test", port=8884, username="yaku-backend", usar_tls=True))
    db.commit()


def test_provisionamiento_incluye_la_credencial_del_dispositivo_y_el_broker_del_panel(
    db, equipo, broker_panel
):
    _guardar(db, equipo, f"dev-{equipo.disp.id_dispositivo}", "clave-del-equipo-1")

    prov = firmwareServ.get_provisioningServ(equipo.disp.id_dispositivo, db, equipo.admin)

    mqtt = prov["mqtt"]
    assert mqtt["username"] == f"dev-{equipo.disp.id_dispositivo}"
    assert mqtt["password"] == "clave-del-equipo-1"
    assert mqtt["host"] == "broker.panel.test"
    assert mqtt["port"] == 8884
    assert mqtt["tls"] is True


def test_provisionamiento_sin_broker_configurado_se_bloquea(db, equipo, broker_panel):
    _guardar(db, equipo, f"dev-{equipo.disp.id_dispositivo}", "clave-del-equipo-1")
    fila = db.query(mqtt_config).one()
    fila.host = ""
    db.commit()

    with pytest.raises(HTTPException) as exc:
        firmwareServ.get_provisioningServ(equipo.disp.id_dispositivo, db, equipo.admin)
    assert exc.value.status_code == 409
    assert "Configuración MQTT" in exc.value.detail


def test_provisionamiento_sin_tls_se_bloquea(db, equipo, broker_panel):
    # Los firmwares solo se conectan con TLS: sin él el equipo quedaría incomunicado.
    _guardar(db, equipo, f"dev-{equipo.disp.id_dispositivo}", "clave-del-equipo-1")
    fila = db.query(mqtt_config).one()
    fila.usar_tls = False
    db.commit()

    with pytest.raises(HTTPException) as exc:
        firmwareServ.get_provisioningServ(equipo.disp.id_dispositivo, db, equipo.admin)
    assert exc.value.status_code == 409
    assert "TLS" in exc.value.detail


def test_provisionamiento_sin_credencial_se_bloquea(db, equipo, broker_panel):
    with pytest.raises(HTTPException) as exc:
        firmwareServ.get_provisioningServ(equipo.disp.id_dispositivo, db, equipo.admin)
    assert exc.value.status_code == 409
    assert "credencial MQTT" in exc.value.detail


# ---------------------------------------------------------------------------
# Clave del backend (mqtt_config)
# ---------------------------------------------------------------------------


def test_clave_del_broker_se_guarda_cifrada_y_el_backend_la_lee_en_claro(
    db, equipo, broker_panel, monkeypatch
):
    import src.main.tasks.mqttSubscriberTask as mqtt_task

    reconexiones = []
    monkeypatch.setattr(mqtt_task, "reiniciar_mqtt", lambda cfg: reconexiones.append(cfg))
    fila = db.query(mqtt_config).one()
    fila.fecha_actualizacion = datetime(2020, 1, 1)
    db.commit()

    mqttConfigServ.actualizar_mqtt_configServ(
        MqttConfigUpdate(host="broker.panel.test", port=8884, username="yaku-backend",
                         password="clave-backend-1", usar_tls=True),
        db=db,
        current_user=equipo.admin,
    )

    db.expire_all()
    fila = db.query(mqtt_config).one()
    assert fila.password.startswith("enc:v1:")
    assert fila.fecha_actualizacion > datetime(2020, 1, 1)  # "Última actualización" cambia
    assert reconexiones[0]["password"] == "clave-backend-1"
    assert mqttConfigServ.obtener_configuracion_efectiva(db)["password"] == "clave-backend-1"


def test_clave_del_broker_en_claro_sigue_funcionando_y_no_se_reescribe(db, broker_panel):
    fila = db.query(mqtt_config).one()
    fila.password = "clave-antigua-en-claro"
    db.commit()

    assert mqttConfigServ.obtener_configuracion_efectiva(db)["password"] == "clave-antigua-en-claro"
    db.expire_all()
    assert db.query(mqtt_config).one().password == "clave-antigua-en-claro"
