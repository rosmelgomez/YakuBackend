"""Contratos de datos del módulo webpush."""

from pydantic import BaseModel


class KeysModel(BaseModel):
    p256dh: str
    auth: str


class SubscribeModel(BaseModel):
    endpoint: str
    keys: KeysModel
