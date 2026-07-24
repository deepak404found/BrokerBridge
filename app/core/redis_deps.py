"""Map Redis provider failures onto the API error envelope."""

from __future__ import annotations

from typing import Any, NoReturn

from app.core.errors import AppError
from app.providers.errors import RedisUnavailableError


def raise_redis_unavailable(exc: RedisUnavailableError, *, op: str) -> NoReturn:
    raise AppError(
        "REDIS_UNAVAILABLE",
        f"Redis dependency is down ({op})",
        status_code=503,
        details={"dependency": "redis", "detail": exc.detail},
    ) from exc


async def acquire_lock(
    lock: Any,
    key: str,
    ttl_seconds: float,
    token: str,
    *,
    op: str,
) -> bool:
    try:
        return bool(await lock.acquire(key, ttl_seconds, token))
    except RedisUnavailableError as exc:
        raise_redis_unavailable(exc, op=op)


async def release_lock(lock: Any, key: str, token: str) -> None:
    try:
        await lock.release(key, token)
    except RedisUnavailableError:
        # TTL expiry is the fallback when Redis is already down.
        pass
