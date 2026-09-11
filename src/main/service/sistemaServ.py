"""Comprobación de disponibilidad y sesiones de alertas."""

import logging

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from src.main.core.bffTokens import decode_bff_token
from src.main.core.yakuConfig import ALLOWED_ORIGINS
from src.main.repositories import bffAuthRep, bootstrapRep
from src.main.service.notifications.websocketManagerServ import manager

logger = logging.getLogger(__name__)


def health_readyServ():
    try:
        bootstrapRep.check_connection()
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}


async def websocket_endpointServ(websocket: WebSocket):
    origin = (websocket.headers.get("origin") or "").rstrip("/")
    if ALLOWED_ORIGINS and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008, reason="Origen no autorizado")
        return
    ticket = websocket.query_params.get("ticket", "")
    try:
        payload = decode_bff_token(ticket, audience="yaku-websocket")
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        await websocket.close(code=1008, reason="Ticket invalido")
        return

    from src.main.db.databaseConexion import SessionLocal

    db = SessionLocal()
    try:
        user = bffAuthRep.queryActiveUserResultado(db, user_id)
        if not user:
            await websocket.close(code=1008, reason="Usuario no autorizado")
            return
        is_admin = user.id_rol == 1
    finally:
        db.close()

    await manager.connect(websocket, user_id=user_id, is_admin=is_admin)
    try:
        while True:
            # Mantener la conexión activa esperando cualquier trama (ej. ping)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logger.exception("Error inesperado en WebSocket")
        manager.disconnect(websocket)
