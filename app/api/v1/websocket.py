from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.dependencies import get_client_ip
from app.db.database import async_session_maker
from app.services.websocket_service import create_websocket_service
from app.websocket.manager import manager

logger = logging.getLogger("studymanager_api")

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    ip = get_client_ip(websocket)
    user_agent = websocket.headers.get("user-agent", "N/A")

    await manager.connect(websocket)
    try:
        auth_data = await websocket.receive_text()
        async with async_session_maker() as session:
            service = create_websocket_service(session)
            auth_user = await service.authenticate(auth_data, ip, user_agent)
            if not auth_user:
                await websocket.close(code=4003)
                return

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning("Websocket connection terminated with error: %s", e)
        manager.disconnect(websocket)
