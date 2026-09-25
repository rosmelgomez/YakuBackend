import os

from dotenv import load_dotenv

load_dotenv()


def require_env(name: str, *, min_length: int = 1) -> str:
    value = os.getenv(name, "").strip()
    if len(value) < min_length:
        raise RuntimeError(f"La variable de entorno {name} es obligatoria")
    return value


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"
# Solo UNA instancia por base de datos/broker debe consumir la telemetria MQTT y correr el
# planificador (ML, cierre por tiempo maximo). Un backend local de desarrollo apuntando a la
# misma BD y broker duplicaba cada lectura y podia iniciar riegos por partida doble.
# Con "false" la API sigue funcionando y puede publicar comandos, pero no se suscribe ni riega.
IOT_TASKS_ENABLED = os.getenv("IOT_TASKS_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
}
AUTO_CREATE_TABLES = os.getenv(
    "AUTO_CREATE_TABLES",
    "true",
).lower() in {"1", "true", "yes"}
BFF_JWT_SECRET = require_env("BFF_JWT_SECRET", min_length=32)
COOKIE_SECURE = os.getenv(
    "COOKIE_SECURE", "true" if IS_PRODUCTION else "false"
).lower() in {
    "1",
    "true",
    "yes",
}
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError("COOKIE_SAMESITE debe ser 'lax', 'strict' o 'none'")
# El navegador descarta en silencio una cookie SameSite=None que no sea Secure.
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise RuntimeError("COOKIE_SAMESITE=none requiere COOKIE_SECURE habilitada (HTTPS)")

ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
}
if not IS_PRODUCTION:
    ALLOWED_ORIGINS.update({"http://localhost:3000", "http://127.0.0.1:3000"})
elif not ALLOWED_ORIGINS:
    raise RuntimeError("ALLOWED_ORIGINS es obligatoria en producción")

if IS_PRODUCTION and not COOKIE_SECURE:
    raise RuntimeError("COOKIE_SECURE debe estar habilitada en producción")
