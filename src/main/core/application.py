"""Ciclo de vida de la aplicación FastAPI."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.main.service.bootstrapServ import initialize_backend
from src.main.service.notifications.websocketManagerServ import set_main_loop
from src.main.tasks.mqttSubscriberTask import stop_mqtt


@asynccontextmanager
async def lifespan(_: FastAPI):
    set_main_loop(asyncio.get_running_loop())
    initialize_backend()
    try:
        yield
    finally:
        stop_mqtt()
