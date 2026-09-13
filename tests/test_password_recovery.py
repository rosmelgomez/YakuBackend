from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from src.main.core.dependencies import get_db
from src.main.core.rateLimit import _attempts
from src.main.core.security import hash_password, verify_password
from src.main.model.models import auth_sessions, roles, tokens_usuario, usuarios


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
    tokens_usuario.__table__.create(engine)
    auth_sessions.__table__.create(engine)

    # Crear logs_sistema compatible con SQLite
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE logs_sistema (
                    id INTEGER PRIMARY KEY,
                    id_usuario INTEGER,
                    accion VARCHAR(100) NOT NULL,
                    modulo VARCHAR(50),
                    descripcion TEXT,
                    ip_acceso VARCHAR(45),
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(id_usuario) REFERENCES usuarios(id)
                )
                """
            )
        )
        conn.commit()

    Session = sessionmaker(bind=engine)
    db = Session()

    db.add(roles(id_rol=1, nombre="administrador", descripcion="Admin"))
    db.add(roles(id_rol=2, nombre="agricultor", descripcion="Agricultor"))

    user = usuarios(
        id_usuario=1,
        nombre="Carlos",
        apellido="Mendoza",
        correo="carlos@example.com",
        contrasena=hash_password("AntiguaPassword123"),
        id_rol=2,
        estado=True,
        verificado=False,
    )
    db.add(user)
    db.commit()

    yield db
    db.close()


@pytest.fixture
def client(test_db):
    app.dependency_overrides[get_db] = lambda: test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def test_solicitar_recuperacion_existing_user(client, test_db):
    response = client.post(
        "/auth/recuperar-contrasena/solicitar",
        json={"correo": "Carlos@Example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "código de recuperación" in data["message"]

    user = test_db.query(usuarios).filter(usuarios.correo == "carlos@example.com").first()
    token_reg = (
        test_db.query(tokens_usuario)
        .filter(
            tokens_usuario.id_usuario == user.id_usuario,
            tokens_usuario.tipo == "recuperacion",
        )
        .first()
    )
    assert token_reg is not None
    assert len(token_reg.token) == 6
    assert token_reg.token.isdigit()
    assert token_reg.expira_en is not None
    assert token_reg.expira_en > datetime.now()
    assert token_reg.usado is False


def test_solicitar_recuperacion_nonexistent_user_anti_enumeration(client, test_db):
    response = client.post(
        "/auth/recuperar-contrasena/solicitar",
        json={"correo": "noexiste@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "código de recuperación" in data["message"]


def test_restablecer_contrasena_success(client, test_db):
    # Solicitar recuperación primero
    client.post(
        "/auth/recuperar-contrasena/solicitar",
        json={"correo": "carlos@example.com"},
    )

    user = test_db.query(usuarios).filter(usuarios.correo == "carlos@example.com").first()
    token_reg = (
        test_db.query(tokens_usuario)
        .filter(
            tokens_usuario.id_usuario == user.id_usuario,
            tokens_usuario.tipo == "recuperacion",
            tokens_usuario.usado.is_(False),
        )
        .first()
    )
    assert token_reg is not None
    codigo = token_reg.token

    # Restablecer contraseña
    response = client.post(
        "/auth/recuperar-contrasena/restablecer",
        json={
            "correo": "carlos@example.com",
            "codigo": codigo,
            "nueva_contrasena": "NuevaPassword2026",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "exitosamente" in data["message"]

    test_db.refresh(user)
    test_db.refresh(token_reg)
    assert verify_password("NuevaPassword2026", user.contrasena)
    assert not verify_password("AntiguaPassword123", user.contrasena)
    assert token_reg.usado is True
    assert token_reg.fecha_uso is not None
    assert user.verificado is True


def test_restablecer_contrasena_invalid_code(client, test_db):
    client.post(
        "/auth/recuperar-contrasena/solicitar",
        json={"correo": "carlos@example.com"},
    )

    response = client.post(
        "/auth/recuperar-contrasena/restablecer",
        json={
            "correo": "carlos@example.com",
            "codigo": "999999",
            "nueva_contrasena": "NuevaPassword2026",
        },
    )
    assert response.status_code == 400
    assert "inválido o inexistente" in response.json()["detail"]


def test_restablecer_contrasena_expired_code(client, test_db):
    user = test_db.query(usuarios).filter(usuarios.correo == "carlos@example.com").first()
    exp_token = tokens_usuario(
        id_usuario=user.id_usuario,
        tipo="recuperacion",
        token="123456",
        expira_en=datetime.now() - timedelta(minutes=5),
        usado=False,
    )
    test_db.add(exp_token)
    test_db.commit()

    response = client.post(
        "/auth/recuperar-contrasena/restablecer",
        json={
            "correo": "carlos@example.com",
            "codigo": "123456",
            "nueva_contrasena": "NuevaPassword2026",
        },
    )
    assert response.status_code == 400
    assert "ha expirado" in response.json()["detail"]


def test_restablecer_contrasena_weak_password(client):
    # Too short
    res = client.post(
        "/auth/recuperar-contrasena/restablecer",
        json={
            "correo": "carlos@example.com",
            "codigo": "123456",
            "nueva_contrasena": "Corto1",
        },
    )
    assert res.status_code == 422

    # No number
    res = client.post(
        "/auth/recuperar-contrasena/restablecer",
        json={
            "correo": "carlos@example.com",
            "codigo": "123456",
            "nueva_contrasena": "SoloLetrasMayusculaYMinuscula",
        },
    )
    assert res.status_code == 422
