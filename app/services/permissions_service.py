from __future__ import annotations

import asyncio
import json
import logging
import random

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.group_member import GroupMember
from app.models.user import User

logger = logging.getLogger(__name__)

_PERM_TTL_BASE = 1800
_PERM_TTL_JITTER = 60

_local_locks: dict[str, asyncio.Lock] = {}
_local_locks_mutex = asyncio.Lock()


def _perm_key(identifier: int, platform: str = "telegram") -> str:
    return f"user_perm:{platform}:{identifier}"


async def _get_or_create_lock(key: str) -> asyncio.Lock:
    async with _local_locks_mutex:
        if key not in _local_locks:
            _local_locks[key] = asyncio.Lock()
        return _local_locks[key]


async def _fetch_permissions_from_db(
    identifier: int,
    session: AsyncSession,
    platform: str = "telegram",
) -> dict:
    settings = get_settings()

    if platform == "telegram":
        condition = User.tg_user_id == identifier
        is_superadmin = identifier == settings.developer_id
    elif platform == "vk":
        condition = User.vk_user_id == identifier
        is_superadmin = False
    else:
        condition = User.id == identifier
        is_superadmin = False

    stmt = (
        select(User, GroupMember)
        .outerjoin(GroupMember, GroupMember.user_id == User.id)
        .where(condition)
    )
    result = await session.execute(stmt)
    rows = result.all()

    groups: dict[str, str] = {}
    full_name = ""

    for user_row, member_row in rows:
        if user_row.is_superadmin:
            is_superadmin = True
        if user_row.full_name:
            full_name = user_row.full_name
        if member_row is not None:
            groups[str(member_row.group_id)] = member_row.role

    return {
        "is_superadmin": is_superadmin,
        "groups": groups,
        "full_name": full_name,
    }


async def get_user_permissions(
    identifier: int,
    session: AsyncSession,
    redis: aioredis.Redis,
    platform: str = "telegram",
) -> dict:
    key = _perm_key(identifier, platform)

    cached = await redis.get(key)
    if cached is not None:
        return json.loads(cached)

    lock = await _get_or_create_lock(key)
    async with lock:
        cached = await redis.get(key)
        if cached is not None:
            return json.loads(cached)

        try:
            permissions = await _fetch_permissions_from_db(
                identifier, session, platform
            )
        except Exception:
            logger.exception(
                "Failed to fetch permissions for %s id=%s", platform, identifier
            )
            raise

        ttl = _PERM_TTL_BASE + random.randint(-_PERM_TTL_JITTER, _PERM_TTL_JITTER)
        await redis.set(key, json.dumps(permissions), ex=ttl)
        return permissions


async def invalidate_user_permissions(
    identifier: int,
    redis: aioredis.Redis,
    platform: str = "telegram",
) -> None:
    await redis.delete(_perm_key(identifier, platform))
    if platform == "telegram":
        await redis.delete(f"user_perm:{identifier}")
