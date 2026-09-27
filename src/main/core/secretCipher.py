"""Cifrado reversible de secretos guardados en la base de datos.

Las claves del broker MQTT (del backend y de cada dispositivo) deben poder
leerse de nuevo: el backend las usa para conectarse y el panel de firmware
las envía al ESP32. Por eso no se guardan como hash sino cifradas con Fernet
(AES-128-CBC + HMAC-SHA256) usando CREDENTIALS_ENCRYPTION_KEY de .env.

Una filtración de la base de datos sin el .env no expone las claves. Si se
pierde la variable, las claves guardadas no se pueden recuperar y hay que
registrarlas de nuevo.
"""

import os

from cryptography.fernet import Fernet, InvalidToken

PREFIJO = "enc:v1:"
VARIABLE_CLAVE = "CREDENTIALS_ENCRYPTION_KEY"


class SecretoNoDisponible(RuntimeError):
    """No hay clave de cifrado configurada o el valor no se pudo descifrar."""


def _fernet() -> Fernet:
    clave = os.getenv(VARIABLE_CLAVE, "").strip()
    if not clave:
        raise SecretoNoDisponible(
            f"La variable de entorno {VARIABLE_CLAVE} no está configurada. Genere una con: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(clave.encode())
    except ValueError as exc:
        raise SecretoNoDisponible(
            f"{VARIABLE_CLAVE} no es una clave Fernet válida (32 bytes en base64 urlsafe)."
        ) from exc


def cifrado_disponible() -> bool:
    try:
        _fernet()
        return True
    except SecretoNoDisponible:
        return False


def esta_cifrado(valor: str | None) -> bool:
    return bool(valor) and valor.startswith(PREFIJO)


def cifrar(valor: str) -> str:
    return PREFIJO + _fernet().encrypt(valor.encode("utf-8")).decode("ascii")


def descifrar(valor: str | None) -> str | None:
    """Devuelve el texto plano. Los valores guardados antes de introducir el
    cifrado (sin prefijo) se devuelven tal cual para no romper instalaciones
    existentes."""
    if not valor:
        return valor
    if not esta_cifrado(valor):
        return valor
    try:
        return _fernet().decrypt(valor[len(PREFIJO):].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretoNoDisponible(
            f"No se pudo descifrar una credencial guardada: {VARIABLE_CLAVE} cambió o el valor está dañado."
        ) from exc
