from __future__ import annotations

import time
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import validate_tg_init_data, validate_vk_sign
from app.db.database import DbSession
from app.db.redis_client import RedisClient
from app.repositories.user_repo import UserRepository
from app.services.permissions_service import get_user_permissions
from app.services.user_service import AuthUser

_AUTH_DATE_MAX_AGE = 86400 * 7


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        user_repo: UserRepository,
        redis: aioredis.Redis,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.user_repo = user_repo
        self.redis = redis
        self.settings = settings or get_settings()

    async def authenticate(
        self,
        x_tg_data: str | None,
        x_vk_sign: str | None,
    ) -> AuthUser:
        user_id: int | None = None
        first_name: str = ""
        full_name: str = ""
        username: str | None = None
        platform: str = "telegram"

        if x_tg_data:
            user_dict = validate_tg_init_data(x_tg_data)
            if not user_dict or not user_dict.get("id"):
                raise HTTPException(status_code=401, detail="Invalid Telegram initData")

            auth_date = user_dict.get("auth_date")
            if not auth_date:
                raise HTTPException(
                    status_code=401, detail="Missing auth_date in Telegram data"
                )

            try:
                if time.time() - int(auth_date) > _AUTH_DATE_MAX_AGE:
                    raise HTTPException(
                        status_code=401, detail="Telegram initData expired"
                    )
            except (ValueError, TypeError):
                raise HTTPException(status_code=401, detail="Invalid auth_date format")

            user_id = int(user_dict["id"])
            first_name = user_dict.get("first_name", "")
            last_name = user_dict.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()
            username = user_dict.get("username")
            platform = "telegram"

            permissions = await get_user_permissions(
                user_id, self.session, self.redis, platform="telegram"
            )

        elif x_vk_sign:
            vk_params = validate_vk_sign(x_vk_sign, self.settings.vk_protected_key)
            if not vk_params or "vk_user_id" not in vk_params:
                raise HTTPException(status_code=401, detail="Invalid VK sign")

            vk_user_id = int(vk_params["vk_user_id"])
            user_obj = await self.user_repo.get_by_vk_id(vk_user_id)
            if user_obj is None:
                raise HTTPException(status_code=403, detail="NOT_IN_GROUP")

            user_id = user_obj.tg_user_id or user_obj.vk_user_id or user_obj.id
            full_name = user_obj.full_name
            name_parts = user_obj.full_name.strip().split()
            first_name = (
                name_parts[1]
                if len(name_parts) > 1
                else (name_parts[0] if name_parts else "")
            )
            username = None
            platform = "vk"

            permissions = await get_user_permissions(
                vk_user_id, self.session, self.redis, platform="vk"
            )

        else:
            raise HTTPException(status_code=401, detail="Authentication required")

        cached_name = permissions.get("full_name")
        resolved_full_name = cached_name or full_name or first_name

        return AuthUser(
            id=user_id,
            first_name=first_name,
            full_name=resolved_full_name,
            username=username,
            platform=platform,
            is_superadmin=permissions.get("is_superadmin", False),
            groups_roles=permissions.get("groups", {}),
        )


def get_auth_service(
    db: DbSession,
    redis: RedisClient,
) -> AuthService:
    return AuthService(db, UserRepository(db), redis, get_settings())


AuthSrv = Annotated[AuthService, Depends(get_auth_service)]
