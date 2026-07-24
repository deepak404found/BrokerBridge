from __future__ import annotations

from typing import Any

from redis.asyncio import Redis


class RedisLock:
    """Token-matching distributed lock via Redis SET NX + Lua release."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def acquire(self, key: str, ttl_seconds: float, token: str) -> bool:
        ttl_ms = max(1, int(ttl_seconds * 1000))
        result = await self._redis.set(key, token, nx=True, px=ttl_ms)
        return bool(result)

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

    async def get(self, key: str) -> dict[str, Any] | None:
        import json

        raw = await self._redis.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        import json

        payload = json.dumps(value)
        if ttl_seconds is not None:
            await self._redis.set(key, payload, ex=int(ttl_seconds))
        else:
            await self._redis.set(key, payload)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)
