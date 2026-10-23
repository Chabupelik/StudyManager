from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import verify_internal_secret
from app.services.websocket_service import WebSocketService

router = APIRouter(tags=["internal"])


@router.post(
    "/internal/broadcast_duties",
    dependencies=[Depends(verify_internal_secret)],
)
async def internal_broadcast_duties() -> dict:
    await WebSocketService.broadcast_duties()
    return {"status": "ok"}
