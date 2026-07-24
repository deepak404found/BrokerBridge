from typing import Any
import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence

EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


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
    """In-process EventProvider with publish fan-out to subscribe handlers."""

    def __init__(self, *, consumer_group: str | None = None) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.topic_prefix: str | None = None
        self.topic_map: dict[str, str] | None = None
        self.provider_type = "memory"
        self.consumer_group = consumer_group or "brokerbridge-lab"
        self.closed = False
        self._handlers: list[tuple[set[str] | None, EventHandler]] = []
        self._stop = asyncio.Event()

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        if self.closed:
            raise RuntimeError("MemoryEventProvider is closed")
        self.published.append((topic, event))
        for topics, handler in list(self._handlers):
            if topics is None or topic in topics:
                await handler(topic, event)

    async def subscribe(
        self,
        topics: Sequence[str],
        handler: EventHandler,
        *,
        consumer_group: str | None = None,
    ) -> None:
        if self.closed:
            raise RuntimeError("MemoryEventProvider is closed")
        if consumer_group:
            self.consumer_group = consumer_group
        topic_set = set(topics) if topics else None
        # Replace handlers (one consumer registration per provider instance)
        self._handlers = [(topic_set, handler)]
        for topic, event in list(self.published):
            if topic_set is None or topic in topic_set:
                await handler(topic, event)

    async def run_consumer(self) -> None:
        """Block until aclose — Memory delivers via publish fan-out."""
        self._stop.clear()
        await self._stop.wait()

    async def probe(self) -> dict[str, Any]:
        return {
            "ok": True,
            "provider_type": "memory",
            "published": len(self.published),
            "handlers": len(self._handlers),
            "consumer_group": self.consumer_group,
        }

    async def aclose(self) -> None:
        self.closed = True
        self._handlers.clear()
        self._stop.set()


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
