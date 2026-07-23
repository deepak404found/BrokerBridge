from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BrokerProvider(Protocol):
    async def probe(self) -> dict[str, Any]: ...

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class InfrastructureProvider(Protocol):
    async def probe(self) -> dict[str, Any]: ...

    async def create_ip(self, region: str, **kwargs: Any) -> dict[str, Any]: ...


@runtime_checkable
class CacheProvider(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...


@runtime_checkable
class LockProvider(Protocol):
    async def acquire(self, key: str, ttl_seconds: float, token: str) -> bool: ...

    async def release(self, key: str, token: str) -> bool: ...


@runtime_checkable
class SessionProvider(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None: ...


@runtime_checkable
class EventProvider(Protocol):
    async def publish(self, topic: str, event: dict[str, Any]) -> None: ...
