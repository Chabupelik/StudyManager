from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from starlette.requests import HTTPConnection

from app.core.config import get_settings
from app.db.redis_client import RedisClient
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


RequireAdmin = Annotated[AuthUser, Depends(require_admin)]


async def require_developer(
    current_user: CurrentUser,
) -> AuthUser:
    if not current_user.is_developer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Developer only",
        )
    return current_user


RequireDeveloper = Annotated[AuthUser, Depends(require_developer)]


class GroupRoleChecker:
    def __init__(self, allowed_roles: list[MemberRole | str]) -> None:
        self.allowed_roles: set[str] = {
            r.value if isinstance(r, MemberRole) else str(r) for r in allowed_roles
        }

    async def __call__(
        self,
        group_id: int,
        current_user: CurrentUser,
    ) -> AuthUser:
        if current_user.has_group_role(group_id, self.allowed_roles):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: insufficient role for this group",
        )


require_group_role = GroupRoleChecker


def get_client_ip(request: HTTPConnection) -> str:
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()

    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        return x_real_ip.strip()

    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


class RateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(
        self,
        request: Request,
        redis: RedisClient,
    ) -> None:
        ip = get_client_ip(request)
        path = request.url.path
        key = f"rate_limit:{ip}:{path}"

        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, self.window_seconds, nx=True)
            res = await pipe.execute()

        current_requests = res[0]

        if current_requests > self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много запросов. Подождите, попробуйте позже.",
            )


rate_limiter = RateLimiter(max_requests=60, window_seconds=60)
RateLimit = Annotated[None, Depends(rate_limiter)]


def verify_internal_secret(
    x_internal_secret: Annotated[str | None, Header(alias="X-Internal-Secret")] = None,
) -> None:
    settings = get_settings()
    if settings.internal_secret and x_internal_secret != settings.internal_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )


async def get_request_details(
    request: Request,
    user: CurrentUser,
) -> dict:
    return {
        "ip": get_client_ip(request),
        "user_agent": request.headers.get("user-agent", "N/A"),
        "platform": user.platform,
    }
