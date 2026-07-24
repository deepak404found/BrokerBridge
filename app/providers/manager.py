from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.models.provider_config import ProviderConfig, ProviderKind, ProviderScope, ProviderStatus
from app.providers.broker.mock import MockBrokerProvider
from app.providers.infrastructure.mock import MockInfrastructureProvider
from app.providers.memory import (
    MemoryCache,
    MemoryEventProvider,
    MemoryLock,
    MemoryRateLimit,
    MemorySession,
)


class ProviderManager:
    """Resolves provider adapters from DB config with env fallbacks."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._cache: dict[str, Any] = {}
        self._redis = None

    def invalidate(self, kind: str | None = None) -> None:
        if kind is None:
            self._cache.clear()
        else:
            self._cache.pop(kind, None)

    def _get_redis(self):
        if self._redis is None:
            from redis.asyncio import from_url

            self._redis = from_url(self.settings.redis_url, decode_responses=True)
        return self._redis

    async def _active_type(self, session: AsyncSession | None, kind: ProviderKind) -> str | None:
        if session is None:
            return None
        result = await session.execute(
            select(ProviderConfig).where(
                ProviderConfig.kind == kind,
                ProviderConfig.status == ProviderStatus.active,
            )
        )
        rows = [
            r
            for r in result.scalars().all()
            if r.client_id is None and r.scope_type == ProviderScope.global_
        ]
        row = rows[0] if rows else None
        return row.provider_type if row else None

    async def get_infrastructure_provider(self, session: AsyncSession | None = None) -> Any:
        if "infrastructure" in self._cache:
            return self._cache["infrastructure"]
        ptype = await self._active_type(session, ProviderKind.infrastructure)
        if not ptype:
            ptype = self.settings.infra_provider
        provider = MockInfrastructureProvider() if ptype == "mock" else MockInfrastructureProvider()
        self._cache["infrastructure"] = provider
        return provider

    async def get_broker_provider(self, session: AsyncSession | None = None) -> Any:
        if "broker" in self._cache:
            return self._cache["broker"]
        ptype = await self._active_type(session, ProviderKind.broker_default)
        if not ptype:
            ptype = self.settings.broker_provider
        provider = MockBrokerProvider() if ptype == "mock" else MockBrokerProvider()
        self._cache["broker"] = provider
        return provider

    def get_cache_provider(self) -> MemoryCache:
        return self._cache.setdefault("cache", MemoryCache())

    def get_lock_provider(self) -> Any:
        if "lock" in self._cache:
            return self._cache["lock"]
        if self.settings.lock_provider == "redis":
            from app.providers.redis_adapters import RedisLock

            provider = RedisLock(self._get_redis())
        else:
            provider = MemoryLock()
        self._cache["lock"] = provider
        return provider

    def get_session_provider(self) -> Any:
        if "session" in self._cache:
            return self._cache["session"]
        if self.settings.session_provider == "redis":
            from app.providers.redis_adapters import RedisSession

            provider = RedisSession(self._get_redis())
        else:
            provider = MemorySession()
        self._cache["session"] = provider
        return provider

    def get_rate_limit_provider(self) -> Any:
        if "rate_limit" in self._cache:
            return self._cache["rate_limit"]
        if self.settings.rate_limit_provider == "redis":
            from app.providers.redis_adapters import RedisRateLimit

            provider = RedisRateLimit(self._get_redis())
        else:
            provider = MemoryRateLimit()
        self._cache["rate_limit"] = provider
        return provider

    def get_event_provider(self) -> MemoryEventProvider:
        return self._cache.setdefault("event", MemoryEventProvider())


_manager: ProviderManager | None = None


def get_provider_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager
