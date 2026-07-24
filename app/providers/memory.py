from typing import Any
import time


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self._data[key] = value


class MemoryLock:
    def __init__(self) -> None:
        self._locks: dict[str, str] = {}

    async def acquire(self, key: str, ttl_seconds: float, token: str) -> bool:
        if key in self._locks and self._locks[key] != token:
            return False
        self._locks[key] = token
        return True

    async def release(self, key: str, token: str) -> bool:
        if self._locks.get(key) != token:
            return False
        del self._locks[key]
        return True


class MemorySession:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        return self._data.get(key)

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)


class MemoryEventProvider:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        self.published.append((topic, event))


class MemoryRateLimit:
    """In-process sliding-window counter for pytest."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def _prune(self, key: str, window_seconds: float, now: float) -> list[float]:
        hits = [t for t in self._hits.get(key, []) if now - t < window_seconds]
        self._hits[key] = hits
        return hits

    async def check(self, key: str, *, limit: float, window_seconds: float = 1.0) -> dict[str, Any]:
        now = time.monotonic()
        hits = self._prune(key, window_seconds, now)
        used = float(len(hits))
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

    async def consume(self, key: str, *, limit: float, window_seconds: float = 1.0) -> dict[str, Any]:
        now = time.monotonic()
        hits = self._prune(key, window_seconds, now)
        if len(hits) >= float(limit):
            pressure = 0.0 if limit <= 0 else min(20.0, 20.0 * (len(hits) / float(limit)))
            return {
                "allowed": False,
                "limit": float(limit),
                "used": float(len(hits)),
                "remaining": 0.0,
                "pressure": pressure,
                "window_seconds": window_seconds,
            }
        hits.append(now)
        self._hits[key] = hits
        used = float(len(hits))
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