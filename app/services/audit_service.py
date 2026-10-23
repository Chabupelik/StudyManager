from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.database import DbSession
from app.models.group_member import GroupMember
from app.models.user import User
from app.repositories.audit_repo import AuditRepository
from app.services.user_service import AuthUser
from app.services.websocket_service import WebSocketService


class AuditService:
    def __init__(self, session: AsyncSession, repo: AuditRepository) -> None:
        self.session = session
        self.repo = repo

    async def log_action(
        self,
        admin_name: str,
        action_type: str,
        details: str,
        user_id: int | None = None,
    ) -> None:
        settings = get_settings()
        if user_id == settings.developer_id:
            return

        entry = await self.repo.log_action(admin_name, action_type, details)
        await self.session.commit()

        await WebSocketService.broadcast_new_log(
            {
                "admin_name": entry.admin_name,
                "action_type": entry.action_type,
                "details": entry.details,
                "created_at": entry.created_at,
            }
        )

    async def ping(self, user: AuthUser) -> dict:
        if user.is_admin():
            name = user.display_name
            await self.repo.upsert_admin_online(user.id, name)
            await self.session.commit()
            await WebSocketService.broadcast_admin_status(
                user_id=user.id,
                last_seen=time.time(),
            )
        return {"status": "ok"}

    async def get_admin_users(self, user: AuthUser) -> dict:
        settings = get_settings()
        online_data = await self.repo.get_all_admins_online()

        conditions = [User.is_superadmin.is_(True)]
        if user.is_superadmin:
            conditions.append(GroupMember.role.in_(["headman", "deputy", "curator"]))
        else:
            admin_group_ids = [
                int(gid)
                for gid, role in user.groups_roles.items()
                if role in ["headman", "deputy", "curator"]
            ]
            if admin_group_ids:
                conditions.append(
                    GroupMember.role.in_(["headman", "deputy", "curator"])
                    & GroupMember.group_id.in_(admin_group_ids)
                )

        stmt = (
            select(User.tg_user_id, User.full_name)
            .outerjoin(GroupMember, GroupMember.user_id == User.id)
            .where(or_(*conditions))
            .distinct()
        )
        result = await self.session.execute(stmt)
        admin_users = result.all()

        admins_map = {
            row.tg_user_id: row.full_name for row in admin_users if row.tg_user_id
        }

        if settings.developer_id not in admins_map:
            admins_map[settings.developer_id] = "ID " + str(settings.developer_id)

        now = time.time()
        admins_list = []

        for admin_id, full_name in admins_map.items():
            data = online_data.get(admin_id)
            name = full_name or (data.name if data else f"Пользователь {admin_id}")
            last_seen = data.last_seen if data else 0

            if admin_id == settings.developer_id:
                is_online = False
                last_seen = 0
            else:
                is_online = (now - last_seen) < 65

            admins_list.append(
                {
                    "id": admin_id,
                    "name": name,
                    "is_online": is_online,
                    "last_seen": last_seen,
                }
            )

        admins_list.sort(key=lambda x: x["is_online"], reverse=True)
        return {"admins": admins_list}

    def get_init(self, user: AuthUser) -> dict:
        if not user.groups_roles and not user.is_superadmin:
            raise HTTPException(status_code=403, detail="NOT_IN_GROUP")

        return {
            "role": "admin" if user.is_admin() else "viewer",
            "user": {"id": user.id, "first_name": user.first_name},
        }

    async def get_logs(
        self,
        offset: int = 0,
        limit: int = 20,
        user_filter: str = "all",
        action_filter: str = "all",
    ) -> dict:
        logs, users, actions = await self.repo.get_action_logs(
            offset, limit, user_filter, action_filter
        )
        return {
            "logs": [
                {
                    "id": l.id,
                    "admin_name": l.admin_name,
                    "action_type": l.action_type,
                    "details": l.details,
                    "created_at": l.created_at,
                }
                for l in logs
            ],
            "filter_users": users,
            "filter_actions": actions,
        }

    async def delete_log(self, log_id: int) -> dict:
        await self.repo.delete_action_log(log_id)
        await self.session.commit()
        return {"status": "ok"}


def get_audit_service(db: DbSession) -> AuditService:
    return AuditService(db, AuditRepository(db))


AuditSrv = Annotated[AuditService, Depends(get_audit_service)]


async def log_action(
    session: AsyncSession,
    admin_name: str,
    action_type: str,
    details: str,
    user_id: int | None = None,
) -> None:
    service = AuditService(session, AuditRepository(session))
    await service.log_action(admin_name, action_type, details, user_id=user_id)
