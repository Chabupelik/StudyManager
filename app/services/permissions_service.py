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

_local_locks: dict[int, asyncio.Lock] = {}
_local_locks_mutex = asyncio.Lock()


def _perm_key(tg_user_id: int) -> str:
    return f"user_perm:{tg_user_id}"


def _lock_key(tg_user_id: int) -> str:
    return f"lock:perm:{tg_user_id}"


async def _get_or_create_lock(tg_user_id: int) -> asyncio.Lock:
    async with _local_locks_mutex:
        if tg_user_id not in _local_locks:
            _local_locks[tg_user_id] = asyncio.Lock()
        return _local_locks[tg_user_id]


async def _fetch_permissions_from_db(
    tg_user_id: int,
    session: AsyncSession,
) -> dict:
    settings = get_settings()

    stmt = (
        select(User, GroupMember)
        .outerjoin(GroupMember, GroupMember.user_id == User.id)
        .where(User.tg_user_id == tg_user_id)
    )
    result = await session.execute(stmt)
    rows = result.all()

    is_superadmin = tg_user_id == settings.developer_id
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
    tg_user_id: int,
    session: AsyncSession,
    redis: aioredis.Redis,
) -> dict:
    key = _perm_key(tg_user_id)

    cached = await redis.get(key)
    if cached is not None:
        return json.loads(cached)

    lock = await _get_or_create_lock(tg_user_id)
    async with lock:
        cached = await redis.get(key)
        if cached is not None:
            return json.loads(cached)

        try:
            permissions = await _fetch_permissions_from_db(tg_user_id, session)
        except Exception:
            logger.exception(
                "Failed to fetch permissions from DB for tg_user_id=%s", tg_user_id
            )
            raise

        ttl = _PERM_TTL_BASE + random.randint(-_PERM_TTL_JITTER, _PERM_TTL_JITTER)
        await redis.set(key, json.dumps(permissions), ex=ttl)
        return permissions


async def invalidate_user_permissions(
    tg_user_id: int,
    redis: aioredis.Redis,
) -> None:
    key = _perm_key(tg_user_id)
    await redis.delete(key)
