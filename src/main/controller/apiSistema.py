"""Endpoints de salud y conexión de alertas."""

from fastapi import APIRouter, WebSocket

from src.main.service import sistemaServ

router = APIRouter()


@router.get("/health/live", include_in_schema=False)
def health_live():
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
def health_ready():
    return sistemaServ.health_readyServ()


@router.websocket("/ws/alertas")
async def websocket_endpoint(websocket: WebSocket):
    return await sistemaServ.websocket_endpointServ(websocket)
