import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from types import SimpleNamespace

from main import app
from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.core.rateLimit import _attempts
from src.main.core.security import verify_password
from src.main.model.models import roles, usuarios


@pytest.fixture(autouse=True)
def reset_rate_limits():
    _attempts.clear()
    yield
    _attempts.clear()


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    roles.__table__.create(engine)
    usuarios.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    db = Session()

    # Seed initial roles
    db.add(roles(id_rol=1, nombre="administrador", descripcion="Admin"))
    db.add(roles(id_rol=2, nombre="agricultor", descripcion="Agricultor"))
    db.commit()

    yield db

    db.close()


@pytest.fixture
def client(test_db):
    app.dependency_overrides[get_db] = lambda: test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user_or_bff, None)


def test_public_register_success(client, test_db):
    payload = {
        "nombre": "Pedro Agricultor",
        "correo": "Pedro@Example.com",
        "contrasena": "Secreta12345",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "Usuario registrado con éxito"

    # Verify user in database
    created = test_db.query(usuarios).filter(usuarios.correo == "pedro@example.com").first()
    assert created is not None
    assert created.nombre == "Pedro Agricultor"
    assert created.id_rol == 2  # Agricultor
    assert created.estado is True
    assert created.verificado is True
    assert verify_password("Secreta12345", created.contrasena)


def test_public_register_rejects_duplicate_email(client, test_db):
    payload = {
        "nombre": "Pedro Agricultor",
        "correo": "pedro_dup@example.com",
        "contrasena": "Secreta12345",
    }
    res1 = client.post("/auth/register", json=payload)
    assert res1.status_code == 201

    # Attempt second registration with same email (different case)
    payload["correo"] = "PEDRO_DUP@example.com"
    res2 = client.post("/auth/register", json=payload)
    assert res2.status_code == 400
    assert "ya está registrado" in res2.json()["detail"]


def test_public_register_rejects_weak_passwords(client):
    # Too short (< 10)
    res = client.post("/auth/register", json={
        "nombre": "Test User",
        "correo": "test1@example.com",
        "contrasena": "Short1",
    })
    assert res.status_code == 422

    # No uppercase
    res = client.post("/auth/register", json={
        "nombre": "Test User",
        "correo": "test2@example.com",
        "contrasena": "lowercase12345",
    })
    assert res.status_code == 422

    # No numbers
    res = client.post("/auth/register", json={
        "nombre": "Test User",
        "correo": "test3@example.com",
        "contrasena": "NoNumbersHere!",
    })
    assert res.status_code == 422


def test_admin_create_user_requires_admin_role(client, test_db):
    non_admin_user = SimpleNamespace(id_usuario=99, id_rol=2, correo="user@yaku.com")
    app.dependency_overrides[get_current_user_or_bff] = lambda: non_admin_user

    payload = {
        "nombre": "Nuevo Admin",
        "correo": "nuevo_admin@yaku.com",
        "contrasena": "SuperSecret123",
        "id_rol": 1,
    }
    response = client.post("/admin/usuarios", json=payload)
    assert response.status_code == 403


def test_admin_create_user_success(client, test_db):
    admin_user = SimpleNamespace(id_usuario=1, id_rol=1, correo="admin@yaku.com")
    app.dependency_overrides[get_current_user_or_bff] = lambda: admin_user

    payload = {
        "nombre": "  Ana Admin  ",
        "apellido": "  Gomez  ",
        "correo": "  Ana.Admin@yaku.com  ",
        "contrasena": "ClaveSegura2026",
        "telefono": "  +51987654321  ",
        "id_rol": 1,
    }
    response = client.post("/admin/usuarios", json=payload)
    assert response.status_code == 201
    assert response.json()["success"] is True

    created = test_db.query(usuarios).filter(usuarios.correo == "ana.admin@yaku.com").first()
    assert created is not None
    assert created.nombre == "Ana Admin"
    assert created.apellido == "Gomez"
    assert created.telefono == "+51987654321"
    assert created.id_rol == 1
    assert created.estado is True
    assert verify_password("ClaveSegura2026", created.contrasena)


def test_admin_create_user_rejects_duplicate(client, test_db):
    admin_user = SimpleNamespace(id_usuario=1, id_rol=1, correo="admin@yaku.com")
    app.dependency_overrides[get_current_user_or_bff] = lambda: admin_user

    payload = {
        "nombre": "Existente",
        "correo": "existente@yaku.com",
        "contrasena": "ClaveSegura2026",
        "id_rol": 2,
    }
    res1 = client.post("/admin/usuarios", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/admin/usuarios", json=payload)
    assert res2.status_code == 409
    assert "ya esta registrado" in res2.json()["detail"]
