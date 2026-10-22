from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import (
    decode_access_token,
    validate_tg_init_data,
    validate_vk_sign,
)
from app.db.database import DbSession, async_session_maker
from app.db.redis_client import RedisClient
from app.models.group_member import MemberRole
from app.models.user import User
from app.services.permissions_service import get_user_permissions
from app.services.user_service import UserContext

_AUTH_DATE_MAX_AGE = 86400


async def get_current_user(
    request: Request,
    x_tg_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
    x_vk_sign: str | None = Header(None, alias="X-VK-Sign"),
    authorization: str | None = Header(None),
) -> UserContext:
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
                    pass
            first_name = user_dict.get("first_name", "")
            last_name = user_dict.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()
            return UserContext(
                id=int(user_dict["id"]),
                first_name=first_name,
                full_name=full_name,
                username=user_dict.get("username"),
                platform="telegram",
            )
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    if x_vk_sign:
        settings = get_settings()
        vk_params = validate_vk_sign(x_vk_sign, settings.vk_protected_key)
        if vk_params and "vk_user_id" in vk_params:
            vk_user_id = int(vk_params["vk_user_id"])
            async with async_session_maker() as session:
                result = await session.execute(
                    select(User).where(User.vk_user_id == vk_user_id)
                )
                user_obj = result.scalar_one_or_none()
            if user_obj is None:
                raise HTTPException(status_code=403, detail="NOT_IN_GROUP")
            first_name = (
                user_obj.full_name.split()[1]
                if len(user_obj.full_name.split()) > 1
                else user_obj.full_name
            )
            return UserContext(
                id=user_obj.tg_user_id or user_obj.id,
                first_name=first_name,
                full_name=user_obj.full_name,
                username=None,
                platform="vk",
            )
        raise HTTPException(status_code=401, detail="Invalid VK sign")

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


CurrentUser = Annotated[UserContext, Depends(get_current_user)]


class UserPermissionContext:
    __slots__ = ("full_name", "groups_roles", "is_superadmin", "user")

    def __init__(
        self,
        user: UserContext,
        is_superadmin: bool,
        groups_roles: dict[str, str],
        full_name: str = "",
    ) -> None:
        self.user = user
        self.is_superadmin = is_superadmin
        self.groups_roles = groups_roles
        self.full_name = full_name or user.full_name or user.first_name


async def get_current_user_context(
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
) -> UserPermissionContext:
    permissions = await get_user_permissions(user.id, session, redis)
    full_name = permissions.get("full_name") or user.full_name or user.first_name
    user.full_name = full_name
    return UserPermissionContext(
        user=user,
        is_superadmin=permissions["is_superadmin"],
        groups_roles=permissions.get("groups", {}),
        full_name=full_name,
    )


CurrentUserContext = Annotated[UserPermissionContext, Depends(get_current_user_context)]


def require_group_role(allowed_roles: list[MemberRole | str]) -> Callable:
    allowed_str: set[str] = {
        r.value if isinstance(r, MemberRole) else str(r) for r in allowed_roles
    }

    async def _check(
        group_id: int,
        ctx: CurrentUserContext,
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


async def require_admin(
    ctx: CurrentUserContext,
) -> UserPermissionContext:
    is_admin = ctx.is_superadmin or any(
        role in ["headman", "deputy", "curator"] for role in ctx.groups_roles.values()
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return ctx


RequireAdmin = Annotated[UserPermissionContext, Depends(require_admin)]


async def require_developer(
    user: CurrentUser,
) -> UserContext:
    if not user.is_developer:
        raise HTTPException(status_code=403, detail="Developer only")
    return user


RequireDeveloper = Annotated[UserContext, Depends(require_developer)]


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_request_details(
    request: Request,
    user: CurrentUser,
) -> dict:
    return {
        "ip": get_client_ip(request),
        "user_agent": request.headers.get("user-agent", "N/A"),
        "platform": user.platform,
    }
