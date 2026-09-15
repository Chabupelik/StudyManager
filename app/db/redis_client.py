from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import get_settings

_redis_pool: aioredis.Redis | None = None


def create_redis_pool() -> aioredis.Redis:
    """
    Create (or return existing) async Redis connection pool.

    Uses redis.asyncio.from_url with a bounded connection pool
    (max_connections=20) so the pool is shared across all requests
    within a single worker process.
    """
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
    """Close the shared pool on application shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


async def get_redis() -> aioredis.Redis:
    """
    FastAPI dependency: yields the shared Redis client.

    Deliberately does NOT use a context-manager yield because the
    pool is long-lived and must not be closed per-request.
    """
    return create_redis_pool()
