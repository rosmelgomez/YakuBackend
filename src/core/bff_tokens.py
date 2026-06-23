import base64
import hashlib
import hmac
import json
import time
from typing import Any

from .config import BFF_JWT_SECRET


def _decode_segment(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def decode_bff_token(token: str, *, audience: str) -> dict[str, Any]:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
        header = json.loads(_decode_segment(header_segment))
        payload = json.loads(_decode_segment(payload_segment))
        provided_signature = _decode_segment(signature_segment)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Token BFF invalido") from exc

    if header != {"alg": "HS256", "typ": "JWT"}:
        raise ValueError("Encabezado BFF invalido")

    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected_signature = hmac.new(
        BFF_JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise ValueError("Firma BFF invalida")

    now = int(time.time())
    if payload.get("type") != "bff" or payload.get("aud") != audience:
        raise ValueError("Audiencia BFF invalida")
    if not isinstance(payload.get("sub"), str) or not payload["sub"].isdigit():
        raise ValueError("Sujeto BFF invalido")
    if not isinstance(payload.get("iat"), int) or not isinstance(payload.get("exp"), int):
        raise ValueError("Vigencia BFF invalida")
    if payload["iat"] > now + 5 or payload["exp"] <= now or payload["exp"] - payload["iat"] > 90:
        raise ValueError("Token BFF vencido o con vigencia invalida")
    if not isinstance(payload.get("jti"), str) or len(payload["jti"]) < 16:
        raise ValueError("Identificador BFF invalido")
    return payload
