from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.dependencies import get_client_ip
from app.services.websocket_service import WebSocketSrv
from app.websocket.manager import manager

logger = logging.getLogger("studymanager_api")

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    service: WebSocketSrv,
) -> None:
    ip = get_client_ip(websocket)
    user_agent = websocket.headers.get("user-agent", "N/A")

    await manager.connect(websocket)
    try:
        auth_data = await websocket.receive_text()
        user = await service.handle_connect(auth_data, ip, user_agent)
        if not user:
            await websocket.close(code=4003)
            return

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning("Websocket connection terminated with error: %s", e)
        manager.disconnect(websocket)
