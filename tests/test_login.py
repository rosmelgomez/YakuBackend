from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from main import app
from src.api.dependencies import get_db
from src.api.routers import auth as auth_router
from src.core.rate_limit import _attempts
from src.core.security import hash_password


VALID_PASSWORD = "ClaveSegura2026"


class FakeQuery:
    def __init__(self, user):
        self.user = user

    def filter(self, *args):
        return self

    def first(self):
        return self.user


class FakeSession:
    def __init__(self, user):
        self.user = user
        self.added = []
        self.commits = 0

    def query(self, model):
        return FakeQuery(self.user)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1


@pytest.fixture(autouse=True)
def reset_login_rate_limit():
    _attempts.clear()
    yield
    _attempts.clear()


@pytest.fixture
def make_client(monkeypatch):
    clients = []
    refresh_session = object()
    monkeypatch.setattr(auth_router, "create_access_token", lambda **kwargs: "access.test.token")
    monkeypatch.setattr(
        auth_router,
        "_new_refresh_token",
        lambda user: ("refresh.test.token", refresh_session),
    )

    def factory(user):
        db = FakeSession(user)
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        clients.append(client)
        return client, db, refresh_session

    yield factory

    app.dependency_overrides.pop(get_db, None)
    for client in clients:
        client.close()


@pytest.fixture
def active_user():
    return SimpleNamespace(
        id_usuario=7,
        nombre="agricultor",
        correo="agricultor@example.com",
        id_rol=2,
        estado=True,
        contrasena=hash_password(VALID_PASSWORD),
    )


def test_login_success_sets_http_only_session_cookies(make_client, active_user):
    client, db, refresh_session = make_client(active_user)

    response = client.post(
        "/auth/login",
        json={"usuario": active_user.correo, "contrasena": VALID_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "Inicio de sesión exitoso"}
    assert response.cookies["access_token"] == "access.test.token"
    assert response.cookies["refresh_token"] == "refresh.test.token"
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    assert all("HttpOnly" in cookie and "SameSite=lax" in cookie for cookie in cookies)
    assert db.added == [refresh_session]
    assert db.commits == 1


def test_login_rejects_wrong_password_without_creating_session(make_client, active_user):
    client, db, _ = make_client(active_user)

    response = client.post(
        "/auth/login",
        json={"usuario": active_user.nombre, "contrasena": "ClaveIncorrecta2026"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Credenciales inválidas"}
    assert db.added == []
    assert db.commits == 0


def test_login_does_not_reveal_that_user_is_unknown(make_client):
    client, db, _ = make_client(None)

    response = client.post(
        "/auth/login",
        json={"usuario": "nadie@example.com", "contrasena": "ClaveIncorrecta2026"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Credenciales inválidas"}
    assert db.added == []
    assert db.commits == 0
