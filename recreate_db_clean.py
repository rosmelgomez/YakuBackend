import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Configurar ruta del proyecto
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

# Parámetros del .env
db_user = os.getenv("DB_USER", "postgres")
db_pass = os.getenv("DB_PASSWORD", "postgres")
db_host = os.getenv("DB_HOST", "127.0.0.1")
db_port = os.getenv("DB_PORT", "5432")
db_name = os.getenv("DB_NAME", "YakuDB")

# 1. Conectar a la base de datos por defecto 'postgres' para recrear 'YakuDB'
postgres_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/postgres"
engine_postgres = create_engine(postgres_url)

print("Intentando eliminar y recrear la base de datos...")
try:
    # Cerramos las conexiones abiertas y destruimos la base de datos
    with engine_postgres.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        print(f"Terminando conexiones a '{db_name}' y eliminándola...")
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE);'))
        print(f"Creando la base de datos '{db_name}' limpia...")
        conn.execute(text(f'CREATE DATABASE "{db_name}";'))
    print("¡Base de datos recreada con éxito!")
except Exception as e:
    print(f"Error al recrear la base de datos: {e}")
    sys.exit(1)

# 2. Inicializar tablas con SQLAlchemy ORM
print("Importando módulos de la aplicación e inicializando tablas ORM...")
try:
    from src.models.database import Base, engine as app_engine
    # Importar los modelos para que Base los conozca antes del create_all
    import src.models.models
    
    # Crear tablas
    Base.metadata.create_all(bind=app_engine)
    print("Tablas creadas correctamente en la base de datos.")
except Exception as e:
    print(f"Error al crear las tablas vía SQLAlchemy: {e}")
    sys.exit(1)

# 3. Sembrar datos
print("Sembrando datos...")
try:
    from seed import ejecutar_semillas
    success = ejecutar_semillas()
    if success:
        print("¡Sembrado completado con éxito!")
    else:
        print("Error durante el sembrado de datos.")
except Exception as e:
    print(f"Error al ejecutar el sembrado: {e}")
    sys.exit(1)
