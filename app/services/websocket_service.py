from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import validate_tg_init_data, validate_vk_sign
from app.db.database import DbSession
from app.models.user import User
from app.repositories.audit_repo import AuditRepository
from app.repositories.user_repo import UserRepository
from app.services.user_service import AuthUser, get_display_name
from app.websocket.manager import manager


class WebSocketService:
    def __init__(
        self,
        session: AsyncSession,
        user_repo: UserRepository,
        audit_repo: AuditRepository,
        settings: Settings,
    ) -> None:
        self.session = session
        self.user_repo = user_repo
        self.audit_repo = audit_repo
        self.settings = settings

    @staticmethod
    async def broadcast_attendance(
        date: str,
        time: str,
        student_id: int,
        status: int,
        reason: str | None,
    ) -> None:
        await manager.broadcast(
            {
                "type": "update_attendance",
                "date": date,
                "time": time,
                "student_id": student_id,
                "status": status,
                "reason": reason,
            }
        )

    @staticmethod
    async def broadcast_day_attendance(date: str, student_id: int) -> None:
        await manager.broadcast(
            {
                "type": "update_day",
                "date": date,
                "student_id": student_id,
            }
        )

    @staticmethod
    async def broadcast_duties() -> None:
        await manager.broadcast({"type": "update_duties"})

    @staticmethod
    async def broadcast_override(date: str) -> None:
        await manager.broadcast({"type": "override", "date": date})

    @staticmethod
    async def broadcast_new_log(entry: dict) -> None:
        await manager.broadcast({"type": "new_log", "entry": entry})

    @staticmethod
    async def broadcast_admin_status(user_id: int, last_seen: float) -> None:
        await manager.broadcast(
            {
                "type": "admin_status",
                "user_id": user_id,
                "last_seen": last_seen,
            }
        )

    async def _log_and_broadcast(
        self,
        admin_name: str,
        action_type: str,
        details: str,
    ) -> None:
        entry = await self.audit_repo.log_action(admin_name, action_type, details)
        await self.session.commit()
        await self.broadcast_new_log(
            {
                "admin_name": entry.admin_name,
                "action_type": entry.action_type,
                "details": entry.details,
                "created_at": entry.created_at,
            }
        )

    async def authenticate(
        self,
        auth_data: str,
        ip: str,
        user_agent: str,
    ) -> AuthUser | None:
        try:
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
                vk_params = validate_vk_sign(auth_data, self.settings.vk_protected_key)
                user_obj: User | None = None
                if vk_params and "vk_user_id" in vk_params:
                    vk_user_id = int(vk_params["vk_user_id"])
                    user_obj = await self.user_repo.get_by_vk_id(vk_user_id)

                if not user_obj:
                    await self._log_and_broadcast(
                        "System",
                        "WS Auth Failed",
                        f"IP: {ip}, Agent: {user_agent}",
                    )
                    return None

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
            if auth_user.id != self.settings.developer_id:
                await self._log_and_broadcast(
                    user_name,
                    "WS Connected",
                    f"IP: {ip}, Platform: {auth_user.platform}, Agent: {user_agent}",
                )

            return auth_user
        finally:
            await self.session.close()


def get_websocket_service(session: DbSession) -> WebSocketService:
    return WebSocketService(
        session=session,
        user_repo=UserRepository(session),
        audit_repo=AuditRepository(session),
        settings=get_settings(),
    )


WebSocketSrv = Annotated[WebSocketService, Depends(get_websocket_service)]
