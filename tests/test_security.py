import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.bff_tokens import decode_bff_token
from src.core.config import BFF_JWT_SECRET
from src.schemas.auth import UserRegisterInput


ROOT = Path(__file__).resolve().parents[1]


def _encode(value: object) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()


def _bff_token(*, audience: str = "yaku-api", issued_at: int | None = None, expires_in: int = 60) -> str:
    now = int(time.time()) if issued_at is None else issued_at
    header = _encode({"alg": "HS256", "typ": "JWT"})
    payload = _encode({
        "sub": "1",
        "aud": audience,
        "type": "bff",
        "iat": now,
        "exp": now + expires_in,
        "jti": "security-test-token-id",
    })
    signing_input = f"{header}.{payload}"
    signature = hmac.new(
        BFF_JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def test_bff_token_accepts_expected_audience():
    assert decode_bff_token(_bff_token(), audience="yaku-api")["sub"] == "1"


def test_bff_token_rejects_tampering_and_wrong_audience():
    token = _bff_token()
    header, payload, signature = token.split(".")
    tampered_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(ValueError):
        decode_bff_token(f"{header}.{payload}.{tampered_signature}", audience="yaku-api")
    with pytest.raises(ValueError):
        decode_bff_token(token, audience="yaku-websocket")


def test_bff_token_rejects_expired_or_excessive_lifetime():
    with pytest.raises(ValueError):
        decode_bff_token(_bff_token(issued_at=int(time.time()) - 120, expires_in=30), audience="yaku-api")
    with pytest.raises(ValueError):
        decode_bff_token(_bff_token(expires_in=600), audience="yaku-api")


def test_public_registration_has_no_role_and_requires_strong_password():
    with pytest.raises(ValidationError):
        UserRegisterInput(
            nombre="Agricultor",
            correo="agricultor@example.com",
            contrasena="Password2026",
            id_rol=1,
        )
    with pytest.raises(ValidationError):
        UserRegisterInput(
            nombre="Agricultor",
            correo="agricultor@example.com",
            contrasena="debil12345",
        )


def test_tracked_sketches_do_not_embed_credentials():
    for filename in ("esp32.ino", "esp32-s3.ino"):
        source = (ROOT / filename).read_text(encoding="utf-8")
        assert '#include "secrets.h"' not in source
        assert 'String wifiPassword = "";' in source
        assert 'String mqttPassword = "";' in source
