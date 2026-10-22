from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select

from app.api.dependencies import (
    CurrentUserContext,
    RequireAdmin,
    RequireDeveloper,
)
from app.core.config import get_settings
from app.db.database import DbSession
from app.models.group_member import GroupMember
from app.models.user import User
from app.repositories.audit_repo import AuditRepository
from app.services.user_service import get_display_name
from app.websocket.manager import manager

router = APIRouter(tags=["admin"])


@router.get("/admin/ping")
async def ping(
    ctx: CurrentUserContext,
    db: DbSession,
):
    is_admin = ctx.is_superadmin or any(
        role in ["headman", "deputy", "curator"] for role in ctx.groups_roles.values()
    )

    if is_admin:
        name = get_display_name(ctx.user)
        repo = AuditRepository(db)
        await repo.upsert_admin_online(ctx.user.id, name)
        await db.commit()

        await manager.broadcast(
            {
                "type": "admin_status",
                "user_id": ctx.user.id,
                "last_seen": time.time(),
            }
        )

    return {"status": "ok"}


@router.get("/admin/users")
async def get_admin_users(
    ctx: RequireAdmin,
    db: DbSession,
):
    settings = get_settings()
    repo = AuditRepository(db)
    online_data = await repo.get_all_admins_online()

    conditions = [User.is_superadmin.is_(True)]

    if ctx.is_superadmin:
        conditions.append(GroupMember.role.in_(["headman", "deputy", "curator"]))
    else:
        admin_group_ids = [
            int(gid)
            for gid, role in ctx.groups_roles.items()
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
    result = await db.execute(stmt)
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


@router.get("/init")
async def get_init(
    ctx: CurrentUserContext,
):
    if not ctx.groups_roles and not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="NOT_IN_GROUP")

    is_admin = ctx.is_superadmin or any(
        role in ["headman", "deputy", "curator"] for role in ctx.groups_roles.values()
    )

    return {
        "role": "admin" if is_admin else "viewer",
        "user": {"id": ctx.user.id, "first_name": ctx.user.first_name},
    }


@router.get("/admin/logs")
async def get_admin_logs(
    ctx: RequireAdmin,
    db: DbSession,
    offset: int = 0,
    limit: int = 20,
    user_filter: str = "all",
    action_filter: str = "all",
):
    repo = AuditRepository(db)
    logs, users, actions = await repo.get_action_logs(
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


@router.delete("/admin/logs/{log_id}")
async def delete_log(
    log_id: int,
    ctx: RequireDeveloper,
    db: DbSession,
):
    repo = AuditRepository(db)
    await repo.delete_action_log(log_id)
    await db.commit()
    return {"status": "ok"}
