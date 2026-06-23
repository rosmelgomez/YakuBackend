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
BFF_JWT_SECRET = require_env("BFF_JWT_SECRET", min_length=32)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true" if IS_PRODUCTION else "false").lower() in {
    "1",
    "true",
    "yes",
}
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
