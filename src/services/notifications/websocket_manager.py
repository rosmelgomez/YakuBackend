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

    async def connect(self, websocket: WebSocket, *, user_id: int, is_admin: bool) -> None:
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
