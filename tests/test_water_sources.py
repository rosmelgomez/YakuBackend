from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.main.core.waterSource import source_firmware_config
from src.main.dtos.ubicacionDto import FuenteAguaCreate, FuenteAguaResponseModel
from src.main.model.models import fuentes_agua
from src.main.service.ubicacionServ import registrar_fuente_aguaServ
from src.main.service.waterMeasurementServ import measurement_method


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    fuentes_agua.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.mark.parametrize("kind", ["manguera", "conexion_directa", " CONEXION_DIRECTA "])
def test_direct_source_api_storage_and_firmware(db, kind):
    payload = FuenteAguaCreate(nombre="Directa", tipo=kind, altura_seguridad_cm=10)
    source = registrar_fuente_aguaServ(payload, db, SimpleNamespace(id_usuario=1))
    response = FuenteAguaResponseModel.model_validate(source)
    assert response.tipo == "conexion_directa"
    assert response.capacidad_litros is None
    assert response.altura_tanque_cm is None
    assert response.altura_seguridad_cm is None
    assert source_firmware_config(source) == {"tipo_fuente": "manguera"}
    assert measurement_method(SimpleNamespace(), source) == "flujometro"


def test_tank_units_and_zero_safety_survive_round_trip(db):
    source = registrar_fuente_aguaServ(FuenteAguaCreate(
        nombre="Tanque", tipo="tanque", capacidad_litros=1500,
        altura_tanque_cm=100, altura_seguridad_cm=0,
    ), db, SimpleNamespace(id_usuario=1))
    response = FuenteAguaResponseModel.model_validate(source)
    assert response.capacidad_litros == 1500
    assert response.capacidad_m3 == 1.5
    assert source_firmware_config(source)["altura_seguridad_cm"] == 0


@pytest.mark.parametrize("overrides", [
    {"tipo": "rio"}, {"capacidad_litros": None}, {"capacidad_litros": 0},
    {"capacidad_litros": float("nan")}, {"altura_tanque_cm": -1},
    {"altura_tanque_cm": float("inf")}, {"altura_seguridad_cm": 50},
    {"altura_seguridad_cm": -1}, {"nombre": "   "},
])
def test_invalid_source_rejected(overrides):
    values = dict(nombre="Tanque", tipo="tanque", capacidad_litros=100, altura_tanque_cm=50)
    with pytest.raises(ValidationError):
        FuenteAguaCreate(**(values | overrides))


@pytest.mark.parametrize("values", [
    {"tipo": "manguera"}, {"tipo": "otro"},
    {"tipo": "conexion_directa", "altura_seguridad_cm": 10},
    {"tipo": "tanque", "altura_tanque_cm": 50},
    {"tipo": "tanque", "altura_tanque_cm": 50, "capacidad_litros": -5},
])
def test_database_rejects_inconsistent_source(db, values):
    db.add(fuentes_agua(id_usuario=1, nombre="Inválida", **values))
    with pytest.raises(IntegrityError):
        db.commit()


def test_missing_source_does_not_invent_measurement_or_tank_dimensions():
    assert source_firmware_config(None) == {"tipo_fuente": ""}
    with pytest.raises(ValueError, match="no tiene fuente"):
        measurement_method(SimpleNamespace())
