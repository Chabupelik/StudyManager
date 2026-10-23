from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.api.dependencies import get_client_ip
from app.core.security import validate_tg_init_data
from app.db.database import async_session_maker
from app.db.redis_client import get_raw_redis_client
from app.repositories.audit_repo import AuditRepository
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.user_service import get_display_name
from app.websocket.manager import manager

logger = logging.getLogger("studymanager_api")

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    ip = get_client_ip(websocket)
    user_agent = websocket.headers.get("user-agent", "N/A")

    await manager.connect(websocket)
    try:
        auth_data = await websocket.receive_text()
        async with async_session_maker() as session:
            auth_service = AuthService(
                session=session,
                user_repo=UserRepository(session),
                redis=get_raw_redis_client(),
            )
            audit_service = AuditService(session, AuditRepository(session))

            try:
                tg_user = validate_tg_init_data(auth_data)
                if tg_user:
                    auth_user = await auth_service.authenticate(
                        x_tg_data=auth_data, x_vk_sign=None
                    )
                else:
                    auth_user = await auth_service.authenticate(
                        x_tg_data=None, x_vk_sign=auth_data
                    )
            except HTTPException:
                await audit_service.log_action(
                    "System",
                    "WS Auth Failed",
                    f"IP: {ip}, Agent: {user_agent}",
                )
                await websocket.close(code=4003)
                return

            user_name = get_display_name(auth_user)
            await audit_service.log_action(
                user_name,
                "WS Connected",
                f"IP: {ip}, Platform: {auth_user.platform}, Agent: {user_agent}",
                user_id=auth_user.id,
            )

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning("Websocket connection terminated with error: %s", e)
        manager.disconnect(websocket)
