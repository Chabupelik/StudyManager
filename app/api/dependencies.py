from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import (
    validate_tg_init_data,
    validate_vk_sign,
)
from app.db.database import DbSession
from app.db.redis_client import RedisClient
from app.models.group_member import MemberRole
from app.models.user import User
from app.services.permissions_service import get_user_permissions
from app.services.user_service import AuthUser

_AUTH_DATE_MAX_AGE = 86400


async def get_current_user(
    request: Request,
    session: DbSession,
    redis: RedisClient,
    x_tg_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
    x_vk_sign: str | None = Header(None, alias="X-VK-Sign"),
) -> AuthUser:
    user_id: int | None = None
    first_name: str = ""
    full_name: str = ""
    username: str | None = None
    platform: str = "telegram"

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
            user_id = int(user_dict["id"])
            first_name = user_dict.get("first_name", "")
            last_name = user_dict.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()
            username = user_dict.get("username")
            platform = "telegram"
        else:
            raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    elif x_vk_sign:
        settings = get_settings()
        vk_params = validate_vk_sign(x_vk_sign, settings.vk_protected_key)
        if vk_params and "vk_user_id" in vk_params:
            vk_user_id = int(vk_params["vk_user_id"])
            result = await session.execute(
                select(User).where(User.vk_user_id == vk_user_id)
            )
            user_obj = result.scalar_one_or_none()
            if user_obj is None:
                raise HTTPException(status_code=403, detail="NOT_IN_GROUP")
            user_id = user_obj.tg_user_id or user_obj.id
            full_name = user_obj.full_name
            first_name = (
                user_obj.full_name.split()[1]
                if len(user_obj.full_name.split()) > 1
                else user_obj.full_name
            )
            username = None
            platform = "vk"
        else:
            raise HTTPException(status_code=401, detail="Invalid VK sign")

    else:
        raise HTTPException(status_code=401, detail="Authentication required")

    permissions = await get_user_permissions(user_id, session, redis)
    cached_name = permissions.get("full_name")
    resolved_full_name = cached_name or full_name or first_name

    return AuthUser(
        id=user_id,
        first_name=first_name,
        full_name=resolved_full_name,
        username=username,
        platform=platform,
        is_superadmin=permissions["is_superadmin"],
        groups_roles=permissions.get("groups", {}),
    )


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]
CurrentUserContext = CurrentUser
UserPermissionContext = AuthUser


async def require_admin(
    current_user: CurrentUser,
) -> AuthUser:
    if not current_user.is_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


RequireAdmin = Annotated[AuthUser, Depends(require_admin)]


async def require_developer(
    current_user: CurrentUser,
) -> AuthUser:
    if not current_user.is_developer:
        raise HTTPException(status_code=403, detail="Developer only")
    return current_user


RequireDeveloper = Annotated[AuthUser, Depends(require_developer)]


def require_group_role(allowed_roles: list[MemberRole | str]) -> Callable:
    allowed_str: set[str] = {
        r.value if isinstance(r, MemberRole) else str(r) for r in allowed_roles
    }

    async def _check(
        group_id: int,
        current_user: CurrentUser,
    ) -> AuthUser:
        if current_user.has_group_role(group_id, allowed_str):
            return current_user
        raise HTTPException(
            status_code=403,
            detail="Forbidden: insufficient role for this group",
        )

    return _check


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
