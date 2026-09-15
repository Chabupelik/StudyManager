from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    decode_access_token,
    validate_tg_init_data,
    validate_vk_sign,
)
from app.data.students_data import STAFF, STUDENTS
from app.db.database import get_db
from app.db.redis_client import get_redis
from app.models.group_member import MemberRole
from app.services.permissions_service import get_user_permissions
from app.services.user_service import UserContext

_AUTH_DATE_MAX_AGE = 86400  # 24 hours — Telegram recommendation


# ---------------------------------------------------------------------------
# Low-level: resolve the caller's identity (platform-agnostic)
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    x_tg_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
    x_vk_sign: str | None = Header(None, alias="X-VK-Sign"),
    authorization: str | None = Header(None),
) -> UserContext:
    """Resolve caller identity from Telegram initData, VK sign, or JWT Bearer."""

    # 1. Telegram initData
    if x_tg_data:
        user_dict = validate_tg_init_data(x_tg_data)
        if user_dict and user_dict.get("id"):
            auth_date = user_dict.get("auth_date")
            if auth_date:
                try:
                    if time.time() - int(auth_date) > _AUTH_DATE_MAX_AGE:
                        raise HTTPException(
                            status_code=401, detail="Telegram initData expired"
                        )
                except (ValueError, TypeError):
                    pass  # non-critical if auth_date is malformed
            return UserContext(
                id=int(user_dict["id"]),
                first_name=user_dict.get("first_name", ""),
                username=user_dict.get("username"),
                platform="telegram",
            )
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    # 2. VK sign — resolve vk_user_id → UserContext
    if x_vk_sign:
        settings = get_settings()
        vk_params = validate_vk_sign(x_vk_sign, settings.vk_protected_key)
        if vk_params and "vk_user_id" in vk_params:
            vk_user_id = int(vk_params["vk_user_id"])
            person = next(
                (p for p in STUDENTS + STAFF if p.get("vk_id") == vk_user_id), None
            )
            if person is None:
                raise HTTPException(status_code=403, detail="NOT_IN_GROUP")
            return UserContext(
                id=person["tg_id"],
                first_name=person["name"].split()[1]
                if len(person["name"].split()) > 1
                else person["name"],
                username=None,
                platform="vk",
            )
        raise HTTPException(status_code=401, detail="Invalid VK sign")

    # 3. JWT Bearer (PC web / tests)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        payload = decode_access_token(token)
        if payload and (sub := payload.get("sub")):
            try:
                return UserContext(id=int(sub), platform="web")
            except ValueError:
                pass
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    raise HTTPException(status_code=401, detail="Authentication required")


# ---------------------------------------------------------------------------
# Rich user context: identity + permissions from Redis/Postgres
# ---------------------------------------------------------------------------


class UserPermissionContext:
    """
    Enriched request context bundling identity and permission data.

    Attributes:
        user:           raw UserContext (id, first_name, platform, …)
        is_superadmin:  True if the user is marked superadmin in DB OR their
                        tg_user_id matches DEVELOPER_ID in config.
        groups_roles:   Mapping of group_id (str) → role (str) for every
                        group this user belongs to.
    """

    __slots__ = ("user", "is_superadmin", "groups_roles")

    def __init__(
        self,
        user: UserContext,
        is_superadmin: bool,
        groups_roles: dict[str, str],
    ) -> None:
        self.user = user
        self.is_superadmin = is_superadmin
        self.groups_roles = groups_roles


async def get_current_user_context(
    user: Annotated[UserContext, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> UserPermissionContext:
    """
    FastAPI dependency: resolves the caller's identity and fetches (or caches)
    their group-role permissions from Redis/Postgres.
    """
    permissions = await get_user_permissions(user.id, session, redis)
    return UserPermissionContext(
        user=user,
        is_superadmin=permissions["is_superadmin"],
        groups_roles=permissions.get("groups", {}),
    )


# ---------------------------------------------------------------------------
# Role-gate factory
# ---------------------------------------------------------------------------


def require_group_role(allowed_roles: list[MemberRole | str]) -> Callable:
    """
    Dependency factory for group-scoped role checks.

    Usage::

        @router.get("/groups/{group_id}/attendance")
        async def get_attendance(
            group_id: int,
            ctx: Annotated[UserPermissionContext,
                           Depends(require_group_role([MemberRole.headman,
                                                       MemberRole.deputy]))],
        ): ...

    Resolution order:
    1. ``is_superadmin`` — always permitted.
    2. Role in *group_id* is in *allowed_roles* — permitted.
    3. Otherwise — 403 Forbidden.
    """
    # Normalise to plain strings so comparison works regardless of whether
    # callers pass MemberRole enum members or raw strings.
    allowed_str: set[str] = {
        r.value if isinstance(r, MemberRole) else str(r) for r in allowed_roles
    }

    async def _check(
        group_id: int,
        ctx: UserPermissionContext = Depends(get_current_user_context),
    ) -> UserPermissionContext:
        if ctx.is_superadmin:
            return ctx
        user_role = ctx.groups_roles.get(str(group_id))
        if user_role and user_role in allowed_str:
            return ctx
        raise HTTPException(
            status_code=403,
            detail="Forbidden: insufficient role for this group",
        )

    return _check


# ---------------------------------------------------------------------------
# Legacy gates — kept for backward compatibility with existing endpoints
# ---------------------------------------------------------------------------


async def require_admin(user: UserContext = Depends(get_current_user)) -> UserContext:
    """Deprecated: checks admin_ids list from config. Prefer require_group_role."""
    settings = get_settings()
    if user.id not in settings.admin_ids_list and user.id != settings.developer_id:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def require_developer(
    user: UserContext = Depends(get_current_user),
) -> UserContext:
    """Permits access only to the developer (DEVELOPER_ID in config)."""
    if not user.is_developer:
        raise HTTPException(status_code=403, detail="Developer only")
    return user


async def get_request_details(
    request: Request, user: UserContext = Depends(get_current_user)
) -> dict:
    ip = request.headers.get("x-forwarded-for")
    if ip:
        ip = ip.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "Unknown"
    return {
        "ip": ip,
        "user_agent": request.headers.get("user-agent", "N/A"),
        "platform": user.platform,
    }
