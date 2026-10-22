from __future__ import annotations

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends

from app.core.config import get_settings

_redis_pool: aioredis.Redis | None = None


def create_redis_pool() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
        _redis_pool = aioredis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return _redis_pool


async def close_redis_pool() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


async def get_redis() -> aioredis.Redis:
    return create_redis_pool()


RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]
