"""Endpoints de salud y conexión de alertas."""

from fastapi import APIRouter, Depends, WebSocket

from src.main.core.bffAuth import get_current_user_or_bff
from src.main.service import sistemaServ

router = APIRouter()


@router.get("/health/live", include_in_schema=False)
def health_live():
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
def health_ready():
    return sistemaServ.health_readyServ()


@router.post("/ws-ticket")
def ws_ticket(current_user=Depends(get_current_user_or_bff)):
    """Emite un ticket de corta duración para abrir el WebSocket de alertas."""
    return sistemaServ.ws_ticketServ(current_user)


@router.websocket("/ws/alertas")
async def websocket_endpoint(websocket: WebSocket):
    return await sistemaServ.websocket_endpointServ(websocket)
