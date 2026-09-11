"""Guardas de arquitectura y flujos HTTP con persistencia aislada."""

import ast
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import app
from src.main.core.access import require_crop_access
from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.core.rateLimit import _attempts
from src.main.core.security import verify_password
from src.main.model import models
from src.main.repositories import backupRep

MAIN = Path(__file__).resolve().parents[1] / "src" / "main"


@pytest.mark.parametrize("layer", ["controller", "service", "repositories", "dtos"])
def test_layer_dependencies(layer):
    for path in (MAIN / layer).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if layer == "controller":
                    assert not module.startswith(
                        ("src.main.model", "src.main.repositories")
                    ), path
                elif layer == "service":
                    assert not module.startswith("src.main.controller"), path
                    if module == "fastapi":
                        assert not {a.name for a in node.names} & {
                            "Depends",
                            "APIRouter",
                        }, path
                elif layer == "repositories":
                    assert not module.startswith(
                        (
                            "src.main.service",
                            "src.main.controller",
                            "src.main.tasks",
                            "fastapi",
                        )
                    ), path
                elif layer == "dtos":
                    assert not module.startswith(
                        ("src.main.service", "src.main.repositories", "src.main.model")
                    ), path
            if layer in {"controller", "service"} and isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and isinstance(
                    node.func.value, ast.Name
                ):
                    assert not (
                        node.func.value.id == "db"
                        and node.func.attr
                        in {"query", "execute", "add", "delete", "commit"}
                    ), (path, node.lineno)
            if layer == "controller" and isinstance(node, ast.ClassDef):
                assert "BaseModel" not in [ast.unparse(base) for base in node.bases], (
                    path
                )


@pytest.fixture
def storage_client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for model in (
        models.roles,
        models.usuarios,
        models.auth_sessions,
        models.regiones,
        models.provincias,
        models.distritos,
        models.almacenes,
        models.plantas,
        models.tipos_metrica,
        models.umbrales_planta,
        models.tipos_dispositivo,
        models.dispositivos,
        models.tipos_componente,
        models.componentes,
        models.cultivos,
    ):
        model.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    identity = SimpleNamespace(id_usuario=1, id_rol=1)
    overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user_or_bff] = lambda: identity
    _attempts.clear()
    # Do not enter the application lifespan: these tests must not start MQTT or migrations.
    client = TestClient(app)
    try:
        yield client, db, identity
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)
        _attempts.clear()
        db.close()
        engine.dispose()


def test_register_persists_farmer_with_hashed_password_and_rejects_duplicate(
    storage_client,
):
    client, db, _ = storage_client
    payload = {
        "nombre": "Agricultor",
        "correo": "farmer@example.com",
        "contrasena": "ClaveSegura2026",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    user = db.query(models.usuarios).one()
    assert user.id_rol == 2
    assert user.contrasena != payload["contrasena"]
    assert verify_password(payload["contrasena"], user.contrasena)
    assert client.post("/auth/register", json=payload).status_code == 400
    assert db.query(models.usuarios).count() == 1


def test_profile_password_change_revokes_refresh_sessions(storage_client):
    client, db, _ = storage_client
    client.post(
        "/auth/register",
        json={
            "nombre": "Agricultor",
            "correo": "farmer@example.com",
            "contrasena": "ClaveSegura2026",
        },
    )
    user = db.query(models.usuarios).one()
    db.add(
        models.auth_sessions(
            session_id="session-to-revoke",
            id_usuario=user.id_usuario,
            token_hash="old-token",
            expires_at=datetime.now() + timedelta(days=1),
        )
    )
    db.commit()
    app.dependency_overrides[get_current_user_or_bff] = lambda: user
    response = client.put(
        "/auth/perfil",
        json={
            "nombre": "Agricultor actualizado",
            "correo": user.correo,
            "contrasena": "OtraClave2026",
        },
    )
    assert response.status_code == 200
    db.expire_all()
    assert db.query(models.auth_sessions).one().revoked is True
    assert verify_password("OtraClave2026", db.query(models.usuarios).one().contrasena)


def test_warehouse_permissions_duplicates_and_delete(storage_client):
    client, db, identity = storage_client
    identity.id_rol = 2
    assert client.post("/almacenes", json={"nombre": "Central"}).status_code == 403
    assert db.query(models.almacenes).count() == 0
    identity.id_rol = 1
    created = client.post("/almacenes", json={"nombre": "Central"})
    assert created.status_code == 201
    warehouse_id = created.json()["id"]
    assert client.post("/almacenes", json={"nombre": "Central"}).status_code == 400
    assert client.get("/almacenes").json()[0]["nombre"] == "Central"
    assert client.delete(f"/almacenes/{warehouse_id}").status_code == 200
    assert client.delete(f"/almacenes/{warehouse_id}").status_code == 404


def test_warehouse_with_stock_cannot_be_deleted(storage_client):
    client, db, _ = storage_client
    warehouse = models.almacenes(nombre="Con stock")
    db.add(warehouse)
    db.flush()
    db.add(models.dispositivos(id_tipo=1, nombre="Sensor", id_almacen=warehouse.id))
    db.commit()
    response = client.delete(f"/almacenes/{warehouse.id}")
    assert response.status_code == 400
    assert db.query(models.almacenes).count() == 1
    assert db.query(models.dispositivos).count() == 1


def test_plant_thresholds_replace_update_clear_and_reject_duplicates(storage_client):
    client, db, _ = storage_client
    response = client.post(
        "/plantas",
        json={
            "nombre": "Lechuga",
            "umbrales": [
                {"id_tipo_metrica": 1, "valor_minimo": 30, "valor_maximo": 70},
                {"id_tipo_metrica": 2, "valor_minimo": 15, "valor_maximo": 25},
            ],
        },
    )
    assert response.status_code == 201
    plant_id = response.json()["id"]
    url = f"/plantas/{plant_id}/umbrales"
    assert (
        client.put(
            url, json=[{"id_tipo_metrica": 1}, {"id_tipo_metrica": 1}]
        ).status_code
        == 400
    )
    assert db.query(models.umbrales_planta).count() == 2
    assert (
        client.put(
            url, json=[{"id_tipo_metrica": 2, "valor_minimo": 18, "valor_maximo": 28}]
        ).status_code
        == 200
    )
    threshold = db.query(models.umbrales_planta).one()
    assert threshold.id_tipo_metrica == 2
    assert float(threshold.valor_minimo) == 18
    assert client.get("/plantas").json()[0]["umbrales"][0]["valor_maximo"] == 28
    assert client.put(url, json=[]).status_code == 200
    assert db.query(models.umbrales_planta).count() == 0


def test_crop_access_respects_owner_and_admin(storage_client):
    _, db, identity = storage_client
    crop = models.cultivos(id_usuario=2, nombre_planta="Tomate")
    db.add(crop)
    db.commit()
    identity.id_rol = 2
    with pytest.raises(HTTPException) as error:
        require_crop_access(db, identity, crop.id_cultivo)
    assert error.value.status_code == 404
    identity.id_usuario = 2
    assert require_crop_access(db, identity, crop.id_cultivo).id_usuario == 2
    identity.id_usuario, identity.id_rol = 1, 1
    assert require_crop_access(db, identity, crop.id_cultivo).id_usuario == 2


def test_backup_authorization_download_and_failure(storage_client, monkeypatch):
    client, _, identity = storage_client
    calls = []

    def export(db):
        calls.append(db)
        return "SELECT 1;", "yaku_backup.sql"

    monkeypatch.setattr(backupRep, "exportarBackup", export)
    identity.id_rol = 2
    assert client.get("/admin/backup").status_code == 403
    assert not calls
    identity.id_rol = 1
    response = client.get("/admin/backup")
    assert response.status_code == 200
    assert response.text == "SELECT 1;"
    assert "filename=yaku_backup.sql" in response.headers["content-disposition"]

    def fail(db):
        raise backupRep.BackupError("fallo simulado")

    monkeypatch.setattr(backupRep, "exportarBackup", fail)
    assert client.get("/admin/backup").status_code == 500
