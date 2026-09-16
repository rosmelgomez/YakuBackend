import asyncio
import threading
from dataclasses import dataclass

from fastapi import WebSocket


@dataclass
class AlertConnection:
    websocket: WebSocket
    user_id: int
    is_admin: bool


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[AlertConnection] = []

    async def connect(
        self, websocket: WebSocket, *, user_id: int, is_admin: bool
    ) -> None:
        await websocket.accept()
        self.active_connections.append(AlertConnection(websocket, user_id, is_admin))

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections = [
            connection
            for connection in self.active_connections
            if connection.websocket is not websocket
        ]

    async def broadcast(self, data: dict, *, user_id: int) -> None:
        stale: list[WebSocket] = []
        for connection in self.active_connections:
            if connection.user_id != user_id and not connection.is_admin:
                continue
            try:
                await connection.websocket.send_json(data)
            except Exception:
                stale.append(connection.websocket)
        for websocket in stale:
            self.disconnect(websocket)


manager = ConnectionManager()

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Registra el event loop principal de FastAPI.

    Callbacks de paho-mqtt corren en un hilo propio sin event loop; para
    despachar el broadcast hacia las conexiones (creadas en el loop
    principal) hace falta cruzar el hilo con run_coroutine_threadsafe en
    vez de crear un loop nuevo (que no puede tocar sockets de otro loop).
    """
    global _main_loop
    _main_loop = loop


def broadcast_ws_event(payload: dict, user_id: int) -> None:
    try:
        running_loop: asyncio.AbstractEventLoop | None
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None and running_loop is _main_loop:
            running_loop.create_task(manager.broadcast(payload, user_id=user_id))
        elif _main_loop is not None and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(payload, user_id=user_id), _main_loop
            )
        elif running_loop is not None:
            running_loop.create_task(manager.broadcast(payload, user_id=user_id))
        else:
            asyncio.run(manager.broadcast(payload, user_id=user_id))
    except Exception:
        pass

