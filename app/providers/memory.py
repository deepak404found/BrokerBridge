from typing import Any


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
