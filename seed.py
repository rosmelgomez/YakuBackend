import os
import re
import sys
from sqlalchemy import text

# Agregar la ruta del proyecto al PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.models.database import engine

def ejecutar_semillas() -> bool:
    # Buscar yaku_data.sql en varias posibles ubicaciones
    posibles_rutas = [
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
        print("Error: No se encontró yaku_data.sql")
        return False
    
    print(f"Leyendo semillas de {sql_path}...")
    try:
        with open(sql_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as read_err:
        print(f"Error al leer el archivo SQL: {read_err}")
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

    print(f"Encontrados {len(statements)} comandos SQL.")
    
    try:
        with engine.begin() as conn:
            for i, stmt in enumerate(statements):
                stmt_clean = stmt.strip()
                if not stmt_clean:
                    continue
                try:
                    conn.execute(text(stmt_clean))
                except Exception as stmt_err:
                    print(f"Error en comando SQL #{i+1}: {stmt_clean[:120]}...")
                    print(f"Detalle del error: {stmt_err}")
                    raise stmt_err
        print("¡Base de datos sembrada con éxito!")
        
        # Restablecer secuencias de ID de forma automática
        print("Restableciendo secuencias de IDs en PostgreSQL...")
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
            print("Secuencias restablecidas correctamente.")
        return True
    except Exception as e:
        print(f"Error sembrando la base de datos: {e}")
        return False

if __name__ == "__main__":
    ejecutar_semillas()
