from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine

from src.main.model.models import usuarios, alertas
from src.main.repositories import bootstrapRep
from src.main.service import bootstrapServ


def test_tables_exist_check():
    engine = create_engine("sqlite:///:memory:")
    with patch.object(bootstrapRep, "engine", engine):
        assert not bootstrapRep.tables_exist()

        # Create the tables that tables_exist checks
        usuarios.__table__.create(engine)
        assert not bootstrapRep.tables_exist()

        alertas.__table__.create(engine)
        assert bootstrapRep.tables_exist()


def test_initialize_backend_calls_create_tables_when_tables_missing():
    mock_create_tables = MagicMock()
    mock_run_migrations = MagicMock()
    mock_ensure_base_catalogs = MagicMock()
    mock_ensure_default_admin = MagicMock()
    mock_ensure_irrigation = MagicMock()
    mock_ensure_feedback = MagicMock()

    with patch.object(bootstrapRep, "tables_exist", return_value=False), \
         patch.object(bootstrapRep, "create_tables", mock_create_tables), \
         patch.object(bootstrapRep, "run_migrations", mock_run_migrations), \
         patch.object(bootstrapRep, "ensure_base_catalogs", mock_ensure_base_catalogs), \
         patch.object(bootstrapRep, "ensure_default_admin", mock_ensure_default_admin), \
         patch.object(bootstrapRep, "ensure_irrigation_execution_schema", mock_ensure_irrigation), \
         patch.object(bootstrapRep, "ensure_feedback_schema", mock_ensure_feedback), \
         patch("src.main.service.bootstrapServ.start_mqtt"), \
         patch("src.main.service.firmwareServ.sincronizar_firmwares_disco"), \
         patch("src.main.tasks.schedulerTask.start_scheduler"):

        # Even with AUTO_CREATE_TABLES=False, it must call create_tables because tables_exist is False
        with patch("src.main.service.bootstrapServ.AUTO_CREATE_TABLES", False), \
             patch("src.main.service.bootstrapServ.IS_PRODUCTION", True):
            bootstrapServ.initialize_backend()
            mock_create_tables.assert_called_once()
            mock_run_migrations.assert_called_once()
            mock_ensure_default_admin.assert_called_once()


def test_initialize_backend_skips_create_tables_when_tables_exist_and_auto_create_disabled():
    mock_create_tables = MagicMock()
    mock_check_connection = MagicMock()
    mock_run_migrations = MagicMock()
    mock_ensure_base_catalogs = MagicMock()
    mock_ensure_default_admin = MagicMock()
    mock_ensure_irrigation = MagicMock()
    mock_ensure_feedback = MagicMock()

    with patch.object(bootstrapRep, "tables_exist", return_value=True), \
         patch.object(bootstrapRep, "create_tables", mock_create_tables), \
         patch.object(bootstrapRep, "check_connection", mock_check_connection), \
         patch.object(bootstrapRep, "run_migrations", mock_run_migrations), \
         patch.object(bootstrapRep, "ensure_base_catalogs", mock_ensure_base_catalogs), \
         patch.object(bootstrapRep, "ensure_default_admin", mock_ensure_default_admin), \
         patch.object(bootstrapRep, "ensure_irrigation_execution_schema", mock_ensure_irrigation), \
         patch.object(bootstrapRep, "ensure_feedback_schema", mock_ensure_feedback), \
         patch("src.main.service.bootstrapServ.start_mqtt"), \
         patch("src.main.service.firmwareServ.sincronizar_firmwares_disco"), \
         patch("src.main.tasks.schedulerTask.start_scheduler"):

        with patch("src.main.service.bootstrapServ.AUTO_CREATE_TABLES", False), \
             patch("src.main.service.bootstrapServ.IS_PRODUCTION", True):
            bootstrapServ.initialize_backend()
            mock_create_tables.assert_not_called()
            mock_check_connection.assert_called_once()
            mock_run_migrations.assert_called_once()
            mock_ensure_default_admin.assert_called_once()


def test_ensure_default_admin_creates_admin_when_none_exists():
    from sqlalchemy.orm import sessionmaker
    from src.main.model.models import roles, usuarios
    from src.main.core.security import verify_password

    engine = create_engine("sqlite:///:memory:")
    roles.__table__.create(engine)
    usuarios.__table__.create(engine)

    Session = sessionmaker(bind=engine)

    with patch.object(bootstrapRep, "engine", engine), \
         patch.object(bootstrapRep, "SessionLocal", Session):
        bootstrapRep.ensure_default_admin()

        db = Session()
        admin = db.query(usuarios).filter(usuarios.id_rol == 1).first()
        assert admin is not None
        assert admin.correo == "admin@yaku.com"
        assert admin.nombre == "Carlos"
        assert admin.apellido == "Admin"
        assert admin.verificado is True
        assert admin.estado is True
        assert verify_password("password123", admin.contrasena)
        db.close()


def test_ensure_default_admin_idempotent_when_admin_exists():
    from sqlalchemy.orm import sessionmaker
    from src.main.model.models import roles, usuarios
    from src.main.core.security import hash_password

    engine = create_engine("sqlite:///:memory:")
    roles.__table__.create(engine)
    usuarios.__table__.create(engine)

    Session = sessionmaker(bind=engine)
    db = Session()
    existing_admin = usuarios(
        nombre="Super",
        apellido="Admin",
        correo="superadmin@yaku.com",
        contrasena=hash_password("adminSecret2026"),
        id_rol=1,
        verificado=True,
        estado=True,
    )
    db.add(existing_admin)
    db.commit()
    db.close()

    with patch.object(bootstrapRep, "engine", engine), \
         patch.object(bootstrapRep, "SessionLocal", Session):
        bootstrapRep.ensure_default_admin()

        db = Session()
        admin_count = db.query(usuarios).filter(usuarios.id_rol == 1).count()
        assert admin_count == 1
        admin = db.query(usuarios).filter(usuarios.id_rol == 1).first()
        assert admin.correo == "superadmin@yaku.com"
        db.close()

