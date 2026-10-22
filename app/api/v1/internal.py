from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import get_settings
from app.websocket.manager import manager

router = APIRouter(tags=["internal"])


@router.post("/internal/broadcast_duties")
@router.post("/api/internal/broadcast_duties")
async def internal_broadcast_duties(
    request: Request,
    x_internal_secret: str | None = Header(default=None),
):
    app_settings = get_settings()
    secret = x_internal_secret or request.headers.get("X-Internal-Secret", "")
    if app_settings.internal_secret and secret != app_settings.internal_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    await manager.broadcast({"type": "update_duties"})
    return {"status": "ok"}
