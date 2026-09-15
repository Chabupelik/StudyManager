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

_PERM_TTL_BASE = 1800  # seconds (30 min)
_PERM_TTL_JITTER = 60  # ±60 s jitter to prevent cache stampede

# Per-process asyncio locks keyed by tg_user_id.
# Prevents Thundering Herd: at most one coroutine per user ID
# will hit the database on a cache miss within the same worker.
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
    """
    Execute a single JOIN query to build the permissions payload for a user.

    Returns:
        {
            "is_superadmin": bool,
            "groups": {"<group_id>": "<role>", ...}
        }
    """
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

    for user_row, member_row in rows:
        if user_row.is_superadmin:
            is_superadmin = True
        if member_row is not None:
            groups[str(member_row.group_id)] = member_row.role

    return {"is_superadmin": is_superadmin, "groups": groups}


async def get_user_permissions(
    tg_user_id: int,
    session: AsyncSession,
    redis: aioredis.Redis,
) -> dict:
    """
    Return the permissions payload for *tg_user_id*.

    Cache strategy (double-checked locking against Thundering Herd):
    1. Fast path: check Redis — return immediately if hit.
    2. Acquire a per-user asyncio.Lock to serialise concurrent misses
       within the same process.
    3. Re-check Redis (another coroutine may have populated it while we
       waited for the lock).
    4. On a genuine miss: query Postgres, write to Redis with TTL +
       random jitter, release lock.
    """
    key = _perm_key(tg_user_id)

    # 1. Fast path (no lock needed)
    cached = await redis.get(key)
    if cached is not None:
        return json.loads(cached)

    # 2. Acquire local lock for this user ID
    lock = await _get_or_create_lock(tg_user_id)
    async with lock:
        # 3. Double-check after acquiring the lock
        cached = await redis.get(key)
        if cached is not None:
            return json.loads(cached)

        # 4. Cache miss — hit the database
        try:
            permissions = await _fetch_permissions_from_db(tg_user_id, session)
        except Exception:
            logger.exception(
                "Failed to fetch permissions from DB for tg_user_id=%s", tg_user_id
            )
            raise

        ttl = _PERM_TTL_BASE + random.randint(-_PERM_TTL_JITTER, _PERM_TTL_JITTER)
        await redis.set(key, json.dumps(permissions), ex=ttl)
        logger.debug("Permissions cached for tg_user_id=%s ttl=%s", tg_user_id, ttl)
        return permissions


async def invalidate_user_permissions(
    tg_user_id: int,
    redis: aioredis.Redis,
) -> None:
    """
    Evict the cached permissions for *tg_user_id*.

    Must be called after any role change, group membership addition
    or removal so that the next request re-fetches fresh data from Postgres.
    """
    key = _perm_key(tg_user_id)
    await redis.delete(key)
    logger.debug("Permissions cache invalidated for tg_user_id=%s", tg_user_id)
