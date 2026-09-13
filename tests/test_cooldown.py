from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.main.model.models import configuracion_control, usuarios, cultivos
from src.main.service.irrigationServ import get_ml_cooldown_minutes
from src.main.service.controlServ import actualizar_cooldown_riego
import pytest

def test_ml_cooldown_retrieval_and_update():
    engine = create_engine('sqlite:///:memory:')
    tables = [
        usuarios.__table__,
        cultivos.__table__,
        configuracion_control.__table__,
    ]
    for table in tables:
        table.drop(engine, checkfirst=True)
        table.create(engine, checkfirst=True)

    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE logs_sistema (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario INTEGER,
                accion VARCHAR(100) NOT NULL,
                modulo VARCHAR(50),
                descripcion TEXT,
                ip_acceso VARCHAR(45),
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        '''))

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(usuarios(id_usuario=1, nombre='Prueba', correo='p@ex.com', contrasena='x'))
        db.add(cultivos(id_cultivo=1, id_usuario=1, nombre_planta='Tomate'))
        db.commit()

        # By default without configuracion_control, fallback is 30
        assert get_ml_cooldown_minutes(db, 1, 1) == 30

        # Update cooldown to 45
        res = actualizar_cooldown_riego(db, 1, 1, 45)
        assert res['status'] == 'ok'
        assert res['cooldownMinutos'] == 45
        assert get_ml_cooldown_minutes(db, 1, 1) == 45

        # Boundary checks
        with pytest.raises(ValueError, match='entre 1 y 1440'):
            actualizar_cooldown_riego(db, 1, 1, 0)
        with pytest.raises(ValueError, match='entre 1 y 1440'):
            actualizar_cooldown_riego(db, 1, 1, 1441)
    finally:
        db.close()