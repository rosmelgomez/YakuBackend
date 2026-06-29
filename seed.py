import os
import re
import logging
import sys
import glob
from sqlalchemy import text

# Agregar la ruta del proyecto al PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.db.database import engine

logger = logging.getLogger(__name__)


def ejecutar_archivo_sql(sql_path: str) -> bool:
    """Lee y ejecuta un archivo SQL en la base de datos."""
    if not os.path.exists(sql_path):
        logger.error(f"No se encontró el archivo SQL: {sql_path}")
        return False

    logger.info(f"Ejecutando archivo SQL: {sql_path}...")
    try:
        with open(sql_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as read_err:
        logger.error(f"Error al leer el archivo SQL {sql_path}: {read_err}")
        return False

    # Eliminar comentarios de una línea de manera segura para evitar falsos positivos
    content = re.sub(r'--.*', '', content)
    
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

    logger.info(f"Encontrados {len(statements)} comandos SQL en {os.path.basename(sql_path)}.")
    
    try:
        with engine.begin() as conn:
            for i, stmt in enumerate(statements):
                stmt_clean = stmt.strip()
                if not stmt_clean:
                    continue
                try:
                    # El archivo contiene JSONB (`"clave":1`) y unidades `%`.
                    # La API parametrizada de SQLAlchemy/psycopg interpreta ambos;
                    # el cursor sin parametros conserva el SQL literalmente.
                    cursor = conn.connection.cursor()
                    try:
                        cursor.execute(stmt_clean)
                    finally:
                        cursor.close()
                except Exception as stmt_err:
                    logger.error(f"Error en comando SQL #{i+1} de {os.path.basename(sql_path)}: {stmt_clean[:120]}...")
                    logger.error(f"Detalle del error: {stmt_err}")
                    raise stmt_err
        return True
    except Exception:
        logger.exception(f"Error al ejecutar el archivo SQL: {sql_path}")
        return False


def ejecutar_semillas() -> bool:
    # 1. Buscar y ejecutar yaku_data.sql
    posibles_rutas = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "yaku_data.sql")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "yaku_data.sql")),
        "../yaku_data.sql",
        "./yaku_data.sql",
        "c:/Archivos/Code/yaku_data.sql"
    ]
    sql_path = None
    for ruta in posibles_rutas:
        if os.path.exists(ruta):
            sql_path = ruta
            break
            
    if not sql_path:
        logger.error("Error: No se encontró yaku_data.sql")
        return False

    if not ejecutar_archivo_sql(sql_path):
        return False

    # 2. Buscar y ejecutar todos los archivos SQL en el directorio migrations/
    migrations_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "migrations"))
    if os.path.exists(migrations_dir):
        # Listar y ordenar todos los archivos .sql en la carpeta migrations
        sql_pattern = os.path.join(migrations_dir, "*.sql")
        migration_files = sorted(glob.glob(sql_pattern))
        
        logger.info(f"Se encontraron {len(migration_files)} archivos de migración SQL para ejecutar.")
        for migration_file in migration_files:
            if not ejecutar_archivo_sql(migration_file):
                logger.error(f"Fallo al ejecutar la migración: {migration_file}")
                return False
    else:
        logger.warning(f"No se encontró el directorio de migraciones en {migrations_dir}")

    # 3. Restablecer secuencias de ID de forma automática en PostgreSQL
    logger.info("Restableciendo secuencias de IDs en PostgreSQL...")
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                DO $$
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN 
                        SELECT table_name, column_name 
                        FROM information_schema.columns 
                        WHERE table_schema = 'public' 
                          AND column_default LIKE 'nextval%'
                    LOOP
                        EXECUTE 'SELECT setval(pg_get_serial_sequence(''' || r.table_name || ''', ''' || r.column_name || '''), COALESCE(MAX(' || r.column_name || '), 1)) FROM ' || r.table_name;
                    END LOOP;
                END;
                $$;
            """))
            logger.info("Secuencias restablecidas correctamente.")
        return True
    except Exception:
        logger.exception("Error al restablecer secuencias de ID")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    raise SystemExit(0 if ejecutar_semillas() else 1)
