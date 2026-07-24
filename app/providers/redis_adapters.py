from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.providers.errors import RedisUnavailableError

P = ParamSpec("P")
R = TypeVar("R")


def _translate_redis(exc: BaseException) -> RedisUnavailableError:
    detail = f"{type(exc).__name__}: {exc}"[:200]
    return RedisUnavailableError("Redis unavailable", detail=detail)


def _redis_call(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except RedisUnavailableError:
            raise
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            raise _translate_redis(exc) from exc

    return wrapper


class RedisLock:
    """Token-matching distributed lock via Redis SET NX + Lua release."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @_redis_call
    async def acquire(self, key: str, ttl_seconds: float, token: str) -> bool:
        ttl_ms = max(1, int(ttl_seconds * 1000))
        result = await self._redis.set(key, token, nx=True, px=ttl_ms)
        return bool(result)

    @_redis_call
    async def release(self, key: str, token: str) -> bool:
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """
        result = await self._redis.eval(script, 1, key, token)
        return int(result) == 1


class RedisSession:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @_redis_call
    async def get(self, key: str) -> dict[str, Any] | None:
        import json

        raw = await self._redis.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    @_redis_call
    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        import json

        payload = json.dumps(value)
        if ttl_seconds is not None:
            await self._redis.set(key, payload, ex=int(ttl_seconds))
        else:
            await self._redis.set(key, payload)

    @_redis_call
    async def delete(self, key: str) -> None:
        await self._redis.delete(key)


class RedisRateLimit:
    """Redis sliding-window counter (ZSET) keyed as rl:broker:{id}."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def _snapshot(self, key: str, *, limit: float, window_seconds: float) -> dict[str, Any]:
        now = time.time()
        window_start = now - window_seconds
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        results = await pipe.execute()
        used = float(results[1] or 0)
        remaining = max(0.0, float(limit) - used)
        pressure = 0.0 if limit <= 0 else min(20.0, 20.0 * (used / float(limit)))
        return {
            "allowed": used < float(limit),
            "limit": float(limit),
            "used": used,
            "remaining": remaining,
            "pressure": pressure,
            "window_seconds": window_seconds,
        }

    @_redis_call
    async def check(self, key: str, *, limit: float, window_seconds: float = 1.0) -> dict[str, Any]:
        return await self._snapshot(key, limit=limit, window_seconds=window_seconds)

    @_redis_call
    async def consume(self, key: str, *, limit: float, window_seconds: float = 1.0) -> dict[str, Any]:
        snap = await self._snapshot(key, limit=limit, window_seconds=window_seconds)
        if not snap["allowed"]:
            return snap
        now = time.time()
        member = f"{now}:{id(self)}:{now}"
        pipe = self._redis.pipeline()
        pipe.zadd(key, {member: now})
        pipe.expire(key, max(1, int(window_seconds) + 1))
        pipe.zcard(key)
        results = await pipe.execute()
        used = float(results[2] or 0)
        remaining = max(0.0, float(limit) - used)
        pressure = 0.0 if limit <= 0 else min(20.0, 20.0 * (used / float(limit)))
        return {
            "allowed": True,
            "limit": float(limit),
            "used": used,
            "remaining": remaining,
            "pressure": pressure,
            "window_seconds": window_seconds,
        }