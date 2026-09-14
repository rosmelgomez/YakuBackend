from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import app
from src.main.core.bffAuth import get_current_user_or_bff
from src.main.core.dependencies import get_db
from src.main.model import models


@pytest.fixture
def test_setup():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for model in (
        models.roles,
        models.usuarios,
        models.cultivos,
        models.feedback_agricultores,
        models.feedback_preguntas,
        models.feedback_respuestas,
    ):
        model.__table__.create(engine)

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE logs_sistema (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_usuario INTEGER,
                    accion VARCHAR(100),
                    modulo VARCHAR(50),
                    descripcion TEXT,
                    ip_acceso VARCHAR(45),
                    fecha DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.commit()

    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()

    admin_role = models.roles(id_rol=1, nombre="administrador")
    farmer_role = models.roles(id_rol=2, nombre="agricultor")
    db.add_all([admin_role, farmer_role])
    db.commit()

    admin_user = models.usuarios(
        id_usuario=1,
        nombre="Admin",
        correo="admin@yaku.pe",
        contrasena="hashed",
        id_rol=1,
        estado=True,
    )
    farmer_user = models.usuarios(
        id_usuario=2,
        nombre="Agricultor",
        correo="farmer@yaku.pe",
        contrasena="hashed",
        id_rol=2,
        estado=True,
    )
    db.add_all([admin_user, farmer_user])
    db.commit()

    identity = SimpleNamespace(id_usuario=2, id_rol=2)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        return identity

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_or_bff] = override_user

    client = TestClient(app)
    yield client, db, identity

    app.dependency_overrides.clear()
    db.close()


def test_ensure_default_questions_and_list(test_setup):
    client, db, identity = test_setup

    # Agricultor solo ve preguntas activas (5 de las 6)
    identity.id_usuario = 2
    identity.id_rol = 2
    res = client.get("/feedback/preguntas")
    assert res.status_code == 200
    questions = res.json()
    assert len(questions) == 5
    assert questions[0]["tipo"] == "select"
    assert len(questions[0]["opciones"]) == 5
    assert questions[0]["obligatoria"] is True
    assert questions[1]["tipo"] == "rating"

    # Administrador puede ver todas las preguntas incluyendo inactivas
    identity.id_usuario = 1
    identity.id_rol = 1
    res_admin = client.get("/feedback/preguntas?incluir_inactivas=true")
    assert res_admin.status_code == 200
    all_questions = res_admin.json()
    assert len(all_questions) == 6
    assert any(q["activo"] is False for q in all_questions)


def test_admin_crud_preguntas(test_setup):
    client, db, identity = test_setup
    identity.id_usuario = 1
    identity.id_rol = 1

    # Crear nueva pregunta
    payload = {
        "pregunta": "¿Qué cultivo te gustaría agregar?",
        "tipo": "text",
        "obligatoria": False,
        "orden": 7,
        "activo": True,
    }
    res_create = client.post("/feedback/preguntas", json=payload)
    assert res_create.status_code == 201
    created = res_create.json()
    assert created["pregunta"] == payload["pregunta"]
    assert created["tipo"] == "text"
    assert created["obligatoria"] is False
    new_id = created["id"]

    # Actualizar pregunta
    update_payload = {
        "pregunta": "¿Qué nuevos cultivos necesitas?",
        "activo": False,
    }
    res_update = client.patch(f"/feedback/preguntas/{new_id}", json=update_payload)
    assert res_update.status_code == 200
    updated = res_update.json()
    assert updated["pregunta"] == "¿Qué nuevos cultivos necesitas?"
    assert updated["activo"] is False

    # Eliminar pregunta
    res_delete = client.delete(f"/feedback/preguntas/{new_id}")
    assert res_delete.status_code == 200
    assert res_delete.json().get("eliminada") is True


def test_farmer_submit_and_list_feedback(test_setup):
    client, db, identity = test_setup

    # Obtener preguntas activas
    identity.id_usuario = 2
    identity.id_rol = 2
    res_q = client.get("/feedback/preguntas")
    preguntas = res_q.json()

    # Preparar respuestas combinadas (select, rating, text)
    respuestas = []
    for p in preguntas:
        if p["tipo"] == "select":
            respuestas.append({"id_pregunta": p["id"], "respuesta_texto": p["opciones"][0]})
        elif p["tipo"] == "rating":
            respuestas.append({"id_pregunta": p["id"], "calificacion": 5})
        elif p["tipo"] == "text":
            respuestas.append({"id_pregunta": p["id"], "respuesta_texto": "Todo funciona excelente"})

    fb_payload = {
        "comentario": "Comentario general opcional",
        "respuestas": respuestas,
    }

    res_post = client.post("/feedback", json=fb_payload)
    assert res_post.status_code == 201
    feedback_data = res_post.json()
    assert feedback_data["calificacion"] == 5
    assert len(feedback_data["respuestas"]) == len(respuestas)

    # Listar historial de feedback del agricultor
    res_list = client.get("/feedback")
    assert res_list.status_code == 200
    historial = res_list.json()
    assert len(historial) == 1
    assert historial[0]["id"] == feedback_data["id"]


def test_validation_required_questions(test_setup):
    client, db, identity = test_setup
    identity.id_usuario = 2
    identity.id_rol = 2

    # Intentar enviar una calificación inválida o faltante en pregunta obligatoria
    res_q = client.get("/feedback/preguntas")
    preguntas = res_q.json()
    rating_q = next(p for p in preguntas if p["tipo"] == "rating")

    # Enviar rating sin calificacion
    bad_payload = {
        "respuestas": [{"id_pregunta": rating_q["id"], "respuesta_texto": "no es numero"}],
    }
    res = client.post("/feedback", json=bad_payload)
    assert res.status_code == 422


def test_feedback_kpis_admin_and_farmer(test_setup):
    client, db, identity = test_setup

    # 1. El agricultor no debe poder consultar KPIs
    identity.id_usuario = 2
    identity.id_rol = 2
    res_forbidden = client.get("/feedback/kpis")
    assert res_forbidden.status_code == 403

    # 2. Agricultor envía dos feedbacks
    res_q = client.get("/feedback/preguntas")
    preguntas = res_q.json()

    # Feedback 1
    respuestas_1 = []
    for p in preguntas:
        if p["tipo"] == "select":
            respuestas_1.append({"id_pregunta": p["id"], "respuesta_texto": p["opciones"][0]})
        elif p["tipo"] == "rating":
            respuestas_1.append({"id_pregunta": p["id"], "calificacion": 5})
        elif p["tipo"] == "text":
            respuestas_1.append({"id_pregunta": p["id"], "respuesta_texto": "Excelente servicio y plataforma"})

    client.post("/feedback", json={"respuestas": respuestas_1})

    # Feedback 2
    respuestas_2 = []
    for p in preguntas:
        if p["tipo"] == "select":
            respuestas_2.append({"id_pregunta": p["id"], "respuesta_texto": p["opciones"][1] if len(p["opciones"]) > 1 else p["opciones"][0]})
        elif p["tipo"] == "rating":
            respuestas_2.append({"id_pregunta": p["id"], "calificacion": 4})
        elif p["tipo"] == "text":
            respuestas_2.append({"id_pregunta": p["id"], "respuesta_texto": "Muy intuitivo"})

    client.post("/feedback", json={"respuestas": respuestas_2})

    # 3. El administrador consulta los KPIs
    identity.id_usuario = 1
    identity.id_rol = 1

    res_kpis = client.get("/feedback/kpis")
    assert res_kpis.status_code == 200
    data = res_kpis.json()

    assert data["total_feedbacks"] == 2
    assert data["promedio_general"] > 0
    assert len(data["preguntas_kpis"]) >= 5

    # Validar métricas de rating
    rating_kpi = next(k for k in data["preguntas_kpis"] if k["tipo"] == "rating")
    assert rating_kpi["total_respuestas"] == 2
    assert rating_kpi["tasa_respuesta_porcentaje"] == 100.0
    assert rating_kpi["promedio_calificacion"] == 4.5
    assert rating_kpi["distribucion_calificacion"]["5"] == 1
    assert rating_kpi["distribucion_calificacion"]["4"] == 1
    assert rating_kpi["porcentaje_positivas"] == 100.0

    # Validar métricas de select
    select_kpi = next(k for k in data["preguntas_kpis"] if k["tipo"] == "select" and k["activo"])
    assert select_kpi["total_respuestas"] == 2
    assert select_kpi["tasa_respuesta_porcentaje"] == 100.0
    assert select_kpi["opcion_mas_votada"] is not None

    # Validar métricas de text
    text_kpi = next(k for k in data["preguntas_kpis"] if k["tipo"] == "text")
    assert text_kpi["total_respuestas"] == 2
    assert text_kpi["longitud_promedio"] > 0
    assert len(text_kpi["ultimas_respuestas_texto"]) == 2
