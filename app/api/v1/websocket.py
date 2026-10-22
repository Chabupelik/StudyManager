from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.dependencies import get_client_ip
from app.core.config import get_settings
from app.core.security import validate_tg_init_data, validate_vk_sign
from app.db.database import async_session_maker
from app.models.user import User
from app.services.audit_service import log_action
from app.services.user_service import AuthUser, get_display_name
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
        app_settings = get_settings()

        tg_user = validate_tg_init_data(auth_data)
        if tg_user and tg_user.get("id"):
            first_name = tg_user.get("first_name", "")
            last_name = tg_user.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()
            auth_user = AuthUser(
                id=int(tg_user["id"]),
                first_name=first_name,
                full_name=full_name,
                platform="telegram",
            )
        else:
            vk_params = validate_vk_sign(auth_data, app_settings.vk_protected_key)
            user_obj: User | None = None
            if vk_params and "vk_user_id" in vk_params:
                vk_user_id = int(vk_params["vk_user_id"])
                async with async_session_maker() as session:
                    stmt = select(User).where(User.vk_user_id == vk_user_id)
                    res = await session.execute(stmt)
                    user_obj = res.scalar_one_or_none()

            if not user_obj:
                async with async_session_maker() as session:
                    await log_action(
                        session,
                        "System",
                        "WS Auth Failed",
                        f"IP: {ip}, Agent: {user_agent}",
                    )
                await websocket.close(code=4003)
                return

            first_name = (
                user_obj.full_name.split()[1]
                if len(user_obj.full_name.split()) > 1
                else user_obj.full_name
            )
            auth_user = AuthUser(
                id=user_obj.tg_user_id or user_obj.id,
                first_name=first_name,
                full_name=user_obj.full_name,
                platform="vk",
            )

        user_name = get_display_name(auth_user)

        async with async_session_maker() as session:
            await log_action(
                session,
                user_name,
                "WS Connected",
                f"IP: {ip}, Platform: {auth_user.platform}, Agent: {user_agent}",
            )

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning("Websocket connection terminated with error: %s", e)
        manager.disconnect(websocket)
