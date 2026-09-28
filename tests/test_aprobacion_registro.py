"""Aprobacion de solicitudes de auto-registro por parte del administrador."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from src.main.dtos.authDto import AuthModel, UserRegisterInput, VerifyCredentialsInput
from src.main.model.models import roles, tokens_usuario, usuarios
from src.main.repositories import authRep
from src.main.service import authServ, usuarioServ

CONTRASENA = "ClaveSegura123"


@pytest.fixture(autouse=True)
def _sin_correo_ni_rate_limit(monkeypatch):
    enviados = []
    monkeypatch.setattr(authServ, "enforce_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(authServ, "enviar_codigo_verificacion", lambda **k: True)
    monkeypatch.setattr(
        usuarioServ, "enviar_resultado_solicitud_registro", lambda **k: enviados.append(k)
    )
    return enviados


@pytest.fixture()
def admin(db):
    for id_rol, nombre in ((1, "administrador"), (2, "agricultor")):
        if not db.query(roles).filter(roles.id_rol == id_rol).first():
            db.add(roles(id_rol=id_rol, nombre=nombre))
    db.commit()
    return SimpleNamespace(id_rol=1, id_usuario=None, correo="admin@example.com")


def _request():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), cookies={})


def _registrar(db):
    correo = f"agri{uuid.uuid4().hex[:8]}@example.com"
    res = authServ.register_userServ(
        _request(),
        UserRegisterInput(nombre="Agricultor", correo=correo, contrasena=CONTRASENA),
        db=db,
    )
    return db.query(usuarios).filter(usuarios.id_usuario == res["userId"]).one()


def _login(db, user):
    return authServ.loginServ(
        _request(), Response(), AuthModel(usuario=user.correo, contrasena=CONTRASENA), db=db
    )


def test_registro_queda_pendiente_y_no_puede_ingresar(db, admin):
    user = _registrar(db)
    assert user.estado_aprobacion == "pendiente"

    # Verificar el correo con el codigo no concede acceso mientras siga pendiente
    codigo = (
        db.query(tokens_usuario)
        .filter(tokens_usuario.id_usuario == user.id_usuario, tokens_usuario.usado.is_(False))
        .one()
        .token
    )
    with pytest.raises(HTTPException) as exc:
        authServ.verify_credentialsServ(
            _request(), Response(), VerifyCredentialsInput(correo=user.correo, token=codigo), db=db
        )
    assert exc.value.status_code == 403
    assert "pendiente de aprobación" in exc.value.detail
    db.refresh(user)
    assert user.verificado is True

    with pytest.raises(HTTPException) as exc:
        _login(db, user)
    assert exc.value.status_code == 403
    assert "pendiente de aprobación" in exc.value.detail

    # Un token emitido antes de la aprobacion tampoco sirve
    assert authRep.queryGetCurrentUserUser(db, user.id_usuario) is None


def test_admin_aprueba_y_el_agricultor_puede_ingresar(db, admin, _sin_correo_ni_rate_limit):
    user = _registrar(db)
    user.verificado = True
    db.commit()

    pendientes = usuarioServ.listar_solicitudes_registroServ(db=db, current_user=admin)
    assert user.id_usuario in {u.id_usuario for u in pendientes}

    res = usuarioServ.aprobar_solicitud_registroServ(user.id_usuario, db=db, current_user=admin)
    assert res["estado_aprobacion"] == "aprobado"
    assert _sin_correo_ni_rate_limit[-1]["aprobado"] is True
    assert _login(db, user)["status"] == "ok"
    assert authRep.queryGetCurrentUserUser(db, user.id_usuario) is not None


def test_admin_rechaza_con_motivo(db, admin, _sin_correo_ni_rate_limit):
    user = _registrar(db)
    user.verificado = True
    db.commit()

    usuarioServ.rechazar_solicitud_registroServ(
        user.id_usuario, motivo="  Datos no validados  ", db=db, current_user=admin
    )
    db.refresh(user)
    assert user.estado_aprobacion == "rechazado"
    assert user.motivo_rechazo == "Datos no validados"
    assert _sin_correo_ni_rate_limit[-1]["aprobado"] is False

    with pytest.raises(HTTPException) as exc:
        _login(db, user)
    assert exc.value.status_code == 403
    assert "rechazada" in exc.value.detail and "Datos no validados" in exc.value.detail

    # Una solicitud ya revisada no se puede volver a revisar
    with pytest.raises(HTTPException) as exc:
        usuarioServ.aprobar_solicitud_registroServ(user.id_usuario, db=db, current_user=admin)
    assert exc.value.status_code == 409


def test_solo_admin_revisa_solicitudes(db, admin):
    user = _registrar(db)
    agricultor = SimpleNamespace(id_rol=2, id_usuario=user.id_usuario, correo=user.correo)
    with pytest.raises(HTTPException) as exc:
        usuarioServ.aprobar_solicitud_registroServ(user.id_usuario, db=db, current_user=agricultor)
    assert exc.value.status_code == 403


def test_registro_notifica_a_los_administradores(db, admin, monkeypatch):
    from src.main.model.models import tipos_alerta
    from src.main.service import notificacionesServ
    from src.main.service.notifications import alertEngineServ

    if not db.query(tipos_alerta).filter(tipos_alerta.codigo == "USUARIO_REGISTRADO").first():
        db.add(tipos_alerta(codigo="USUARIO_REGISTRADO", nombre="Nuevo usuario registrado",
                            severidad="info", activo=True))
    admin_user = usuarios(nombre="Admin", correo=f"admin{uuid.uuid4().hex[:8]}@example.com",
                          contrasena="x", id_rol=1, estado=True)
    db.add(admin_user)
    db.commit()

    eventos = []
    monkeypatch.setattr(alertEngineServ, "broadcast_ws_event", lambda p, uid: eventos.append(p))

    nuevo = _registrar(db)

    avisos = notificacionesServ.listar_notificacionesServ(db, admin_user)
    aviso = next(a for a in avisos if nuevo.correo in a["mensaje"])
    assert aviso["titulo"] == "Nuevo usuario registrado"
    assert aviso["severidad"] == "info"
    assert aviso["leida"] is False
    assert aviso["link"] == "/dashboard/administrador/usuarios#solicitudes"

    # Un solo aviso en tiempo real, marcado para el rol administrador
    assert [e["rol_destino"] for e in eventos] == ["administrador"]
    assert eventos[0]["link"] == aviso["link"]

    # El agricultor recién registrado no recibe este aviso
    assert notificacionesServ.listar_notificacionesServ(db, nuevo) == []
