from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    UserPermissionContext,
    get_current_user_context,
    require_admin,
    require_developer,
)
from app.core.config import get_settings
from app.db.database import get_db
from app.repositories.audit_repo import AuditRepository
from app.services.user_service import get_display_name
from app.websocket.manager import manager

router = APIRouter(tags=["admin"])


@router.get("/admin/ping")
@router.get("/ping_admin")
async def ping(
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    is_admin = (
        ctx.is_superadmin
        or ctx.user.id in settings.admin_ids_list
        or any(
            role in ["headman", "deputy", "curator"]
            for role in ctx.groups_roles.values()
        )
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
@router.get("/admin_users")
async def get_admin_users(
    ctx: Annotated[UserPermissionContext, Depends(require_admin)],
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    repo = AuditRepository(db)
    online_data = await repo.get_all_admins_online()

    # Query all users who are admins
    from sqlalchemy import select

    from app.models.group_member import GroupMember
    from app.models.user import User

    stmt = (
        select(User.tg_user_id, User.full_name)
        .outerjoin(GroupMember, GroupMember.user_id == User.id)
        .where(
            (User.is_superadmin.is_(True))
            | (User.tg_user_id.in_(settings.admin_ids_list))
            | (GroupMember.role.in_(["headman", "deputy", "curator"]))
        )
        .distinct()
    )
    result = await db.execute(stmt)
    admin_users = result.all()

    # Create a mapping of tg_user_id -> full_name
    admins_map = {
        row.tg_user_id: row.full_name for row in admin_users if row.tg_user_id
    }

    # Ensure developer is always in the list
    if settings.developer_id not in admins_map:
        admins_map[settings.developer_id] = "ID " + str(settings.developer_id)

    # Ensure hardcoded admins from config are always in the list
    for admin_id in settings.admin_ids_list:
        if admin_id not in admins_map:
            admins_map[admin_id] = "ID " + str(admin_id)

    now = time.time()
    admins_list = []

    for admin_id, full_name in admins_map.items():
        data = online_data.get(admin_id)
        name = full_name

        if data:
            # Prefer the name from audit logs (recent interaction)
            name = data.name
        elif admin_id == settings.curator_id:
            name = "Виктория Александровна"

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
@router.get("/admin/init")
async def get_init(
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
):
    if not ctx.groups_roles and not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="NOT_IN_GROUP")

    settings = get_settings()

    # User is an admin if they are superadmin, in admin_ids_list, or have an admin-level role in any group
    is_admin = (
        ctx.is_superadmin
        or ctx.user.id in settings.admin_ids_list
        or any(
            role in ["headman", "deputy", "curator"]
            for role in ctx.groups_roles.values()
        )
    )

    return {
        "role": "admin" if is_admin else "viewer",
        "user": {"id": ctx.user.id, "first_name": ctx.user.first_name},
    }


@router.get("/admin/logs")
@router.get("/logs")
async def get_admin_logs(
    offset: int = 0,
    limit: int = 20,
    user_filter: str = "all",
    action_filter: str = "all",
    ctx: Annotated[UserPermissionContext, Depends(require_admin)] = None,
    db: AsyncSession = Depends(get_db),
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
@router.delete("/logs/{log_id}")
async def delete_log(
    log_id: int,
    ctx: Annotated[UserPermissionContext, Depends(require_developer)] = None,
    db: AsyncSession = Depends(get_db),
):
    repo = AuditRepository(db)
    await repo.delete_action_log(log_id)
    await db.commit()
    return {"status": "ok"}
