from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import validate_tg_init_data
from app.db.database import async_session_maker
from app.db.redis_client import get_raw_redis_client
from app.models.audit import ActionLog
from app.repositories.audit_repo import AuditRepository
from app.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService
from app.services.user_service import AuthUser, get_display_name
from app.websocket.manager import manager

logger = logging.getLogger("studymanager_api")
_background_tasks: set[asyncio.Task] = set()


class WebSocketService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @classmethod
    async def _safe_broadcast(cls, message: dict) -> None:
        task = asyncio.create_task(cls._do_broadcast(message))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    @classmethod
    async def _do_broadcast(cls, message: dict) -> None:
        try:
            await manager.broadcast(message)
        except Exception as e:
            logger.warning("Failed to broadcast websocket event: %s", e)

    @classmethod
    async def broadcast_attendance(
        cls,
        date: str,
        time: str,
        student_id: int,
        status: int,
        reason: str | None,
    ) -> None:
        await cls._safe_broadcast(
            {
                "type": "update_attendance",
                "date": date,
                "time": time,
                "student_id": student_id,
                "status": status,
                "reason": reason,
            }
        )

    @classmethod
    async def broadcast_day_attendance(cls, date: str, student_id: int) -> None:
        await cls._safe_broadcast(
            {
                "type": "update_day",
                "date": date,
                "student_id": student_id,
            }
        )

    @classmethod
    async def broadcast_duties(cls) -> None:
        await cls._safe_broadcast({"type": "update_duties"})

    @classmethod
    async def broadcast_override(cls, date: str) -> None:
        await cls._safe_broadcast({"type": "override", "date": date})

    @classmethod
    async def broadcast_new_log(cls, entry: dict) -> None:
        await cls._safe_broadcast({"type": "new_log", "entry": entry})

    @classmethod
    async def broadcast_admin_status(cls, user_id: int, last_seen: float) -> None:
        await cls._safe_broadcast(
            {
                "type": "admin_status",
                "user_id": user_id,
                "last_seen": last_seen,
            }
        )

    async def _log_and_broadcast(
        self,
        audit_repo: AuditRepository,
        session: AsyncSession,
        admin_name: str,
        action_type: str,
        details: str,
    ) -> ActionLog:
        entry = await audit_repo.log_action(admin_name, action_type, details)
        await session.commit()
        created_at_val = (
            float(entry.created_at.timestamp())
            if hasattr(entry.created_at, "timestamp")
            else float(entry.created_at)
        )
        await self.broadcast_new_log(
            {
                "id": entry.id,
                "admin_name": entry.admin_name,
                "action_type": entry.action_type,
                "details": entry.details,
                "created_at": created_at_val,
            }
        )
        return entry

    async def handle_connect(
        self,
        auth_data: str,
        ip: str,
        user_agent: str,
    ) -> AuthUser | None:
        async with async_session_maker() as session:
            auth_service = AuthService(
                session=session,
                user_repo=UserRepository(session),
                redis=get_raw_redis_client(),
                settings=self.settings,
            )
            audit_repo = AuditRepository(session)

            try:
                if validate_tg_init_data(auth_data):
                    auth_user = await auth_service.authenticate(
                        x_tg_data=auth_data, x_vk_sign=None
                    )
                else:
                    auth_user = await auth_service.authenticate(
                        x_tg_data=None, x_vk_sign=auth_data
                    )
            except HTTPException:
                await self._log_and_broadcast(
                    audit_repo,
                    session,
                    "System",
                    "WS Auth Failed",
                    f"IP: {ip}, Agent: {user_agent}",
                )
                return None

            if auth_user.id != self.settings.developer_id:
                user_name = get_display_name(auth_user)
                await self._log_and_broadcast(
                    audit_repo,
                    session,
                    user_name,
                    "WS Connected",
                    f"IP: {ip}, Platform: {auth_user.platform}, Agent: {user_agent}",
                )

            return auth_user


def get_websocket_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> WebSocketService:
    return WebSocketService(settings=settings)


WebSocketSrv = Annotated[WebSocketService, Depends(get_websocket_service)]
