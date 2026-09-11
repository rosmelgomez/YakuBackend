"""Compatibilidad con despliegues que usan uvicorn main:app."""

from app import app

__all__ = ["app"]
