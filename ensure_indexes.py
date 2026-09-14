import sys
import logging
from sqlalchemy import text
from src.main.db.databaseConexion import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ensure_indexes")

INDEX_QUERIES = [
    "CREATE INDEX IF NOT EXISTS ix_humedad_suelo_asig_fecha ON humedad_suelo (id_asignacion, fecha DESC);",
    "CREATE INDEX IF NOT EXISTS ix_humedad_suelo_asig_valido_fecha ON humedad_suelo (id_asignacion, valido, fecha);",
    "CREATE INDEX IF NOT EXISTS ix_humedad_ambiente_asig_fecha ON humedad_ambiente (id_asignacion, fecha DESC);",
    "CREATE INDEX IF NOT EXISTS ix_humedad_ambiente_asig_valido_fecha ON humedad_ambiente (id_asignacion, valido, fecha);",
    "CREATE INDEX IF NOT EXISTS ix_temperatura_suelo_asig_fecha ON temperatura_suelo (id_asignacion, fecha DESC);",
    "CREATE INDEX IF NOT EXISTS ix_temperatura_suelo_asig_valido_fecha ON temperatura_suelo (id_asignacion, valido, fecha);",
    "CREATE INDEX IF NOT EXISTS ix_temperatura_ambiente_asig_fecha ON temperatura_ambiente (id_asignacion, fecha DESC);",
    "CREATE INDEX IF NOT EXISTS ix_temperatura_ambiente_asig_valido_fecha ON temperatura_ambiente (id_asignacion, valido, fecha);",
    "CREATE INDEX IF NOT EXISTS ix_telemetria_tanque_asig_fecha ON telemetria_tanque (id_asignacion, fecha DESC);",
    "CREATE INDEX IF NOT EXISTS ix_riego_asig_inicio ON riego (id_asignacion, fecha_inicio DESC);",
    "CREATE INDEX IF NOT EXISTS ix_cultivos_user_estado ON cultivos (id_usuario, estado);",
    "CREATE INDEX IF NOT EXISTS ix_asignaciones_iot_user_cultivo ON asignaciones_iot (id_usuario, id_cultivo);",
]

def run():
    logger.info("Verificando y creando índices de alto rendimiento en PostgreSQL...")
    try:
        with engine.connect() as conn:
            for q in INDEX_QUERIES:
                try:
                    conn.execute(text(q))
                    conn.commit()
                    logger.info(f"OK: {q}")
                except Exception as e:
                    logger.warning(f"Advertencia al ejecutar '{q}': {e}")
        logger.info("Índices verificados y creados exitosamente.")
    except Exception as e:
        logger.error(f"Error al conectar con la base de datos: {e}")

if __name__ == "__main__":
    run()
