from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import verify_internal_secret
from app.websocket.manager import manager

router = APIRouter(tags=["internal"])


@router.post(
    "/internal/broadcast_duties",
    dependencies=[Depends(verify_internal_secret)],
)
async def internal_broadcast_duties():
    await manager.broadcast({"type": "update_duties"})
    return {"status": "ok"}
