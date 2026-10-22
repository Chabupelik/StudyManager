from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from app.models.group_member import MemberRole
from app.services.auth_service import AuthSrv
from app.services.user_service import AuthUser


async def get_current_user(
    auth_service: AuthSrv,
    x_tg_data: Annotated[str | None, Header(alias="X-Telegram-Init-Data")] = None,
    x_vk_sign: Annotated[str | None, Header(alias="X-VK-Sign")] = None,
) -> AuthUser:
    return await auth_service.authenticate(x_tg_data, x_vk_sign)


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]


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
