"""Ciclo de vida de la aplicación FastAPI."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.main.service.bootstrapServ import initialize_backend
from src.main.tasks.mqttSubscriberTask import stop_mqtt


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_backend()
    try:
        yield
    finally:
        stop_mqtt()
