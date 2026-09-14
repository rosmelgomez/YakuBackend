"""Preparación del esquema y comprobaciones de PostgreSQL."""

import logging

from sqlalchemy import text

from src.main.db.databaseConexion import Base, SessionLocal, engine
from src.main.model import models

logger = logging.getLogger(__name__)

FEEDBACK_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS feedback_agricultores (
        id SERIAL PRIMARY KEY,
        id_usuario INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        id_cultivo INTEGER REFERENCES cultivos(id) ON DELETE SET NULL,
        modulo VARCHAR(50) NOT NULL,
        tipo VARCHAR(30) NOT NULL,
        calificacion INTEGER NOT NULL,
        mensaje TEXT NOT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'nuevo',
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_feedback_calificacion CHECK (calificacion BETWEEN 1 AND 5)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_feedback_agricultores_id_usuario ON feedback_agricultores(id_usuario)",
    "CREATE INDEX IF NOT EXISTS ix_feedback_agricultores_id_cultivo ON feedback_agricultores(id_cultivo)",
    """
    CREATE TABLE IF NOT EXISTS feedback_preguntas (
        id SERIAL PRIMARY KEY,
        pregunta TEXT NOT NULL,
        tipo VARCHAR(20) NOT NULL DEFAULT 'rating',
        obligatoria BOOLEAN NOT NULL DEFAULT TRUE,
        opciones JSON,
        descripcion TEXT,
        orden INTEGER NOT NULL DEFAULT 0,
        activo BOOLEAN NOT NULL DEFAULT TRUE,
        fecha_registro TIMESTAMP NOT NULL DEFAULT NOW(),
        actualizado_en TIMESTAMP NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_respuestas (
        id SERIAL PRIMARY KEY,
        id_feedback INTEGER NOT NULL REFERENCES feedback_agricultores(id) ON DELETE CASCADE,
        id_pregunta INTEGER NOT NULL REFERENCES feedback_preguntas(id) ON DELETE RESTRICT,
        calificacion INTEGER,
        respuesta_texto TEXT,
        fecha TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_feedback_respuesta_calificacion CHECK (calificacion IS NULL OR (calificacion BETWEEN 1 AND 5)),
        CONSTRAINT uq_feedback_respuesta_pregunta UNIQUE (id_feedback, id_pregunta)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_feedback_respuestas_id_feedback ON feedback_respuestas(id_feedback)",
    "CREATE INDEX IF NOT EXISTS ix_feedback_respuestas_id_pregunta ON feedback_respuestas(id_pregunta)",
    "ALTER TABLE feedback_preguntas ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'rating'",
    "ALTER TABLE feedback_preguntas ADD COLUMN IF NOT EXISTS obligatoria BOOLEAN DEFAULT TRUE",
    "ALTER TABLE feedback_preguntas ADD COLUMN IF NOT EXISTS opciones JSON",
    "ALTER TABLE feedback_respuestas ADD COLUMN IF NOT EXISTS respuesta_texto TEXT",
    "ALTER TABLE feedback_respuestas ALTER COLUMN calificacion DROP NOT NULL",
    """
    INSERT INTO feedback_preguntas (pregunta, tipo, obligatoria, opciones, orden, activo)
    SELECT pregunta, tipo, obligatoria, opciones::json, orden, activo
    FROM (
        VALUES
            ('¿Con qué frecuencia utilizas la plataforma Yaku?', 'select', TRUE, '["Varias veces al día", "Una vez al día", "Varios días a la semana", "Una vez a la semana", "Menos de una vez a la semana"]', 1, TRUE),
            ('¿Cómo valorarías la utilidad del sistema de alertas?', 'rating', TRUE, NULL, 2, TRUE),
            ('¿Las recomendaciones de riego se han ajustado a las necesidades reales de tu cultivo?', 'rating', TRUE, NULL, 3, TRUE),
            ('¿Qué aspecto mejorarías de la plataforma?', 'text', FALSE, NULL, 4, TRUE),
            ('¿Recomendarías Yaku a otros agricultores?', 'rating', TRUE, NULL, 5, TRUE),
            ('¿Qué funcionalidad usas con más frecuencia?', 'select', FALSE, '["Control de riego", "Sensores", "Alertas", "Modelos IA"]', 6, FALSE)
    ) AS defaults(pregunta, tipo, obligatoria, opciones, orden, activo)
    WHERE NOT EXISTS (SELECT 1 FROM feedback_preguntas)
    """,
)

IRRIGATION_EXECUTION_SCHEMA_STATEMENTS = (
    "ALTER TABLE riego ADD COLUMN IF NOT EXISTS segundos_acumulados INT DEFAULT 0",
    "ALTER TABLE riego ADD COLUMN IF NOT EXISTS fecha_inicio TIMESTAMP",
    "ALTER TABLE riego ADD COLUMN IF NOT EXISTS fecha_fin TIMESTAMP",
    """
    CREATE TABLE IF NOT EXISTS ejecuciones_riego (
        id SERIAL PRIMARY KEY,
        id_riego BIGINT NOT NULL REFERENCES riego(id) ON DELETE CASCADE,
        fecha_inicio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        fecha_fin TIMESTAMP,
        distancia_inicial_cm NUMERIC(6,2),
        distancia_final_cm NUMERIC(6,2),
        duracion_segundos INT DEFAULT 0,
        cantidad_agua_litros NUMERIC(10,2) DEFAULT 0.0,
        motivo_cierre VARCHAR(50)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ejecuciones_riego_riego ON ejecuciones_riego(id_riego)",
    "CREATE INDEX IF NOT EXISTS idx_ejecuciones_riego_fecha ON ejecuciones_riego(fecha_inicio DESC)",
)

BASE_CATALOG_STATEMENTS = (
    """
    INSERT INTO roles (id, nombre, descripcion)
    SELECT 1, 'administrador', 'Administrador global del sistema'
    WHERE NOT EXISTS (SELECT 1 FROM roles WHERE id = 1)
    """,
    """
    INSERT INTO roles (id, nombre, descripcion)
    SELECT 2, 'agricultor', 'Usuario final del campo'
    WHERE NOT EXISTS (SELECT 1 FROM roles WHERE id = 2)
    """,
    """
    INSERT INTO tipos_dispositivo (id, nombre, descripcion, metodo_medicion)
    SELECT 1, 'ESP32-S3 (Módulo Colector)', 'Microcontrolador recolector de telemetría de suelo y ambiente.', NULL
    WHERE NOT EXISTS (SELECT 1 FROM tipos_dispositivo WHERE id = 1)
    """,
    """
    INSERT INTO tipos_dispositivo (id, nombre, descripcion, metodo_medicion)
    SELECT 2, 'ESP32 (Actuador con proximidad)', 'Calcula litros por cambio de nivel del tanque.', 'proximidad'
    WHERE NOT EXISTS (SELECT 1 FROM tipos_dispositivo WHERE id = 2)
    """,
    """
    INSERT INTO tipos_dispositivo (id, nombre, descripcion, metodo_medicion)
    SELECT 3, 'ESP32 (Actuador con flujometro)', 'Mide volumen por pulsos del YF-S201.', 'flujometro'
    WHERE NOT EXISTS (SELECT 1 FROM tipos_dispositivo WHERE id = 3)
    """,
)


def run_migrations() -> None:
    import glob
    import os
    import re

    migrations_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "resources", "migrations")
    )
    if not os.path.exists(migrations_dir):
        logger.warning(f"Directorio de migraciones no encontrado: {migrations_dir}")
        return

    sql_pattern = os.path.join(migrations_dir, "*.sql")
    migration_files = sorted(glob.glob(sql_pattern))
    logger.info(
        f"Se encontraron {len(migration_files)} archivos de migración SQL para ejecutar."
    )

    with engine.begin() as conn:
        for migration_file in migration_files:
            logger.info(
                f"Ejecutando migración SQL: {os.path.basename(migration_file)}..."
            )
            try:
                with open(migration_file, "r", encoding="utf-8-sig") as f:
                    content = f.read()
            except Exception as read_err:
                logger.error(
                    f"Error al leer el archivo SQL {migration_file}: {read_err}"
                )
                continue

            # Eliminar comentarios
            content = re.sub(r"--.*", "", content)

            # Separar comandos por punto y coma (;) respetando el fin de línea
            statements = []
            current_stmt = []
            for line in content.splitlines():
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                current_stmt.append(line)
                if line_stripped.endswith(";"):
                    statements.append("\n".join(current_stmt))
                    current_stmt = []

            if current_stmt:
                stmt = "\n".join(current_stmt).strip()
                if stmt:
                    statements.append(stmt)

            cursor = conn.connection.cursor()
            try:
                for stmt in statements:
                    stmt_clean = stmt.strip()
                    if stmt_clean:
                        cursor.execute(stmt_clean)
            except Exception as stmt_err:
                logger.error(
                    f"Error en comando SQL de {os.path.basename(migration_file)}: {stmt_err}"
                )
                raise stmt_err
            finally:
                cursor.close()
    logger.info("Migraciones SQL ejecutadas con éxito.")


def ensure_feedback_schema() -> None:
    with engine.begin() as connection:
        for statement in FEEDBACK_SCHEMA_STATEMENTS:
            try:
                connection.execute(text(statement))
            except Exception as e:
                logger.warning(f"Sentencia feedback: {e}")
    logger.info("Esquema de feedback verificado")


def ensure_irrigation_execution_schema() -> None:
    with engine.begin() as connection:
        for statement in IRRIGATION_EXECUTION_SCHEMA_STATEMENTS:
            connection.execute(text(statement))
    logger.info("Esquema de ejecuciones de riego verificado")


def ensure_base_catalogs() -> None:
    with engine.begin() as connection:
        for statement in BASE_CATALOG_STATEMENTS:
            connection.execute(text(statement))
        if engine.dialect.name == "postgresql":
            try:
                connection.execute(
                    text(
                        "SELECT setval(pg_get_serial_sequence('roles', 'id'), (SELECT COALESCE(MAX(id), 1) FROM roles))"
                    )
                )
                connection.execute(
                    text(
                        "SELECT setval(pg_get_serial_sequence('tipos_dispositivo', 'id'), (SELECT COALESCE(MAX(id), 1) FROM tipos_dispositivo))"
                    )
                )
            except Exception as e:
                logger.warning(f"No se pudo sincronizar secuencias de catalogo: {e}")
    logger.info("Catálogos base verificados")


def ensure_default_admin() -> None:
    """Asegura que exista al menos un usuario administrador en la base de datos."""
    import os
    from src.main.core.security import hash_password

    default_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@yaku.com").strip().lower()
    default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "password123").strip()
    default_nombre = os.getenv("DEFAULT_ADMIN_NAME", "Carlos").strip()
    default_apellido = os.getenv("DEFAULT_ADMIN_LASTNAME", "Admin").strip()
    default_telefono = os.getenv("DEFAULT_ADMIN_PHONE", "+51999888777").strip()

    db = SessionLocal()
    try:
        admin_user = (
            db.query(models.usuarios).filter(models.usuarios.id_rol == 1).first()
        )
        if not admin_user:
            user_by_email = (
                db.query(models.usuarios)
                .filter(models.usuarios.correo == default_email)
                .first()
            )
            if user_by_email:
                user_by_email.id_rol = 1
                user_by_email.estado = True
                user_by_email.verificado = True
                db.commit()
                logger.info(
                    f"Usuario existente '{default_email}' promovido a administrador"
                )
            else:
                hashed_pw = hash_password(default_password)
                new_admin = models.usuarios(
                    nombre=default_nombre,
                    apellido=default_apellido,
                    correo=default_email,
                    contrasena=hashed_pw,
                    id_rol=1,
                    telefono=default_telefono,
                    zona_horaria="America/Lima",
                    verificado=True,
                    estado=True,
                )
                db.add(new_admin)
                db.commit()
                logger.info(
                    f"Administrador por defecto creado exitosamente: {default_email}"
                )

            if engine.dialect.name == "postgresql":
                try:
                    db.execute(
                        text(
                            "SELECT setval(pg_get_serial_sequence('usuarios', 'id'), (SELECT COALESCE(MAX(id), 1) FROM usuarios))"
                        )
                    )
                    db.commit()
                except Exception as seq_err:
                    logger.warning(
                        f"No se pudo sincronizar secuencia de usuarios: {seq_err}"
                    )
        else:
            logger.info("Administrador existente verificado en la base de datos")
    except Exception as e:
        db.rollback()
        logger.error(f"Error al verificar/crear administrador por defecto: {e}")
        raise
    finally:
        db.close()




def tables_exist() -> bool:
    """Verifica si las tablas base del sistema existen en la base de datos."""
    try:
        from sqlalchemy import inspect

        inspector = inspect(engine)
        return inspector.has_table("alertas") and inspector.has_table("usuarios")
    except Exception as e:
        logger.warning(f"Error al verificar existencia de tablas: {e}")
        return False


def create_tables():
    Base.metadata.create_all(bind=engine)


def check_connection():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def database_empty() -> bool:
    """Verifica si la base de datos no tiene los catálogos o usuarios base cargados."""
    db = SessionLocal()
    try:
        no_regiones = db.query(models.regiones).count() == 0
        no_usuarios = db.query(models.usuarios).count() == 0
        return no_regiones or no_usuarios
    except Exception:
        return True
    finally:
        db.close()


def ensure_soil_ambient_umbrales_only():
    """Elimina métricas de nivel de tanque, batería y caudal de la configuración de umbrales."""
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                DELETE FROM configuracion_umbrales 
                WHERE id_tipo_metrica IN (
                    SELECT id FROM tipos_metrica WHERE codigo IN ('NIVEL_AGUA', 'BAT_PCT', 'CAUDAL')
                );
                DELETE FROM umbrales_planta 
                WHERE id_tipo_metrica IN (
                    SELECT id FROM tipos_metrica WHERE codigo IN ('NIVEL_AGUA', 'BAT_PCT', 'CAUDAL')
                );
                """
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"No se pudo limpiar umbrales no ambientales: {e}")
    finally:
        db.close()


def ensure_active_notification_types():
    """Desactiva tipos de alerta de variables fuera de rango y asegura RIEGO_ML y PROBLEMA_RIEGO."""
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                UPDATE tipos_alerta 
                SET activo = FALSE 
                WHERE id IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10) 
                   OR codigo LIKE 'ALERT_%';
                """
            )
        )
        db.execute(
            text(
                """
                INSERT INTO tipos_alerta (id, codigo, nombre, descripcion, severidad, activo)
                SELECT 11, 'RIEGO_ML', 'Riego activado por IA', 'Notificación con los datos de las 4 variables analizadas por el modelo al iniciar el riego.', 'info', TRUE
                WHERE NOT EXISTS (SELECT 1 FROM tipos_alerta WHERE codigo = 'RIEGO_ML');
                """
            )
        )
        db.execute(
            text(
                """
                INSERT INTO tipos_alerta (id, codigo, nombre, descripcion, severidad, activo)
                SELECT 12, 'PROBLEMA_RIEGO', 'Incidencias y problemas de riego', 'Problemas críticos: riego fallido, interrupción, parada sin confirmar o desconexión.', 'critica', TRUE
                WHERE NOT EXISTS (SELECT 1 FROM tipos_alerta WHERE codigo = 'PROBLEMA_RIEGO');
                """
            )
        )
        db.execute(
            text(
                """
                DELETE FROM notificaciones WHERE id_alerta IN (
                    SELECT id FROM alertas WHERE id_tipo_metrica IS NOT NULL OR id_tipo_alerta IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
                );
                DELETE FROM alertas WHERE id_tipo_metrica IS NOT NULL OR id_tipo_alerta IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10);
                """
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"No se pudo asegurar tipos de alerta activos: {e}")
    finally:
        db.close()



