from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.core.crypto import decrypt_secret
from app.models.provider_config import ProviderConfig, ProviderKind, ProviderScope, ProviderStatus
from app.providers.broker.mock import MockBrokerProvider
from app.providers.infrastructure.mock import MockInfrastructureProvider
from app.providers.kafka_event import KafkaEventProvider
from app.providers.memory import (
    MemoryCache,
    MemoryEventProvider,
    MemoryLock,
    MemoryRateLimit,
    MemorySession,
)

logger = logging.getLogger("brokerbridge.providers")


class ProviderManager:
    """Resolves provider adapters from DB config with env fallbacks."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._cache: dict[str, Any] = {}
        self._redis = None
        self._event_version: int | None = None
        self._stale: list[Any] = []

    def invalidate(self, kind: str | None = None) -> None:
        if kind is None:
            for key, provider in list(self._cache.items()):
                if key == "event":
                    self._stale.append(provider)
            self._cache.clear()
            self._event_version = None
            return
        if kind == "event":
            old = self._cache.pop("event", None)
            if old is not None:
                self._stale.append(old)
            self._event_version = None
            return
        self._cache.pop(kind, None)

    async def _close_stale(self) -> None:
        while self._stale:
            provider = self._stale.pop()
            close = getattr(provider, "aclose", None)
            if close is not None:
                try:
                    await close()
                except Exception:  # noqa: BLE001
                    logger.warning("provider_aclose_failed")

    def _get_redis(self):
        if self._redis is None:
            from redis.asyncio import from_url

            self._redis = from_url(self.settings.redis_url, decode_responses=True)
        return self._redis

    async def _active_row(
        self, session: AsyncSession | None, kind: ProviderKind
    ) -> ProviderConfig | None:
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
        return rows[0] if rows else None

    async def _active_type(self, session: AsyncSession | None, kind: ProviderKind) -> str | None:
        row = await self._active_row(session, kind)
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

    def _env_event_config(self) -> tuple[str, dict[str, Any]]:
        """Bootstrap event config from settings (.env). Returns (provider_type, config)."""
        ptype = (self.settings.event_provider or "memory").strip().lower()
        brokers = (self.settings.kafka_bootstrap_servers or "").strip() or (
            self.settings.redpanda_brokers or ""
        ).strip()
        config: dict[str, Any] = {
            "brokers": brokers,
            "security_protocol": self.settings.kafka_security_protocol or "PLAINTEXT",
            "sasl_mechanism": self.settings.kafka_sasl_mechanism or None,
            "ssl": bool(self.settings.kafka_ssl),
            "topic_prefix": self.settings.kafka_topic_prefix or "brokerbridge",
            "username": self.settings.kafka_username or None,
            "password": self.settings.kafka_password or None,
            "consumer_group": self.settings.kafka_consumer_group or None,
        }
        if ptype in {"", "memory"}:
            # Auto-promote to redpanda_local when brokers are set and type left as memory
            # only if EVENT_PROVIDER explicitly redpanda/kafka — keep memory as safe default.
            return "memory", config
        return ptype, config

    def _build_event_provider(self, provider_type: str, config: dict[str, Any]) -> Any:
        ptype = (provider_type or "memory").lower()
        if ptype == "memory":
            return MemoryEventProvider()

        brokers = (
            config.get("brokers")
            or config.get("bootstrap_servers")
            or self.settings.redpanda_brokers
            or ""
        )
        if isinstance(brokers, list):
            brokers = ",".join(str(b) for b in brokers)
        brokers = str(brokers).strip()
        if not brokers:
            logger.warning("event_provider_missing_brokers falling_back=memory type=%s", ptype)
            return MemoryEventProvider()

        topic_map = config.get("topic_map") if isinstance(config.get("topic_map"), dict) else None
        return KafkaEventProvider(
            brokers=brokers,
            security_protocol=str(config.get("security_protocol") or "PLAINTEXT"),
            sasl_mechanism=config.get("sasl_mechanism") or None,
            username=config.get("username") or None,
            password=config.get("password") or None,
            ssl=bool(config.get("ssl", False)),
            topic_prefix=config.get("topic_prefix") or self.settings.kafka_topic_prefix or "brokerbridge",
            topic_map=topic_map,
            provider_type=ptype,
        )

    async def _load_event_secrets(self, row: ProviderConfig) -> dict[str, Any]:
        public = dict(row.config_non_secret or {})
        if not row.config_encrypted:
            return public
        try:
            raw = decrypt_secret(row.config_encrypted, self.settings)
            secrets = json.loads(raw) if raw else {}
            if isinstance(secrets, dict):
                public.update(secrets)
        except Exception:  # noqa: BLE001
            logger.warning("event_config_decrypt_failed version=%s", row.version)
        return public

    async def get_event_provider(self, session: AsyncSession | None = None) -> Any:
        await self._close_stale()

        row = await self._active_row(session, ProviderKind.event)
        if row is not None:
            if "event" in self._cache and self._event_version == row.version:
                return self._cache["event"]
            # Version changed or cold build
            if "event" in self._cache:
                self._stale.append(self._cache.pop("event"))
                await self._close_stale()
            config = await self._load_event_secrets(row)
            provider = self._build_event_provider(row.provider_type, config)
            self._cache["event"] = provider
            self._event_version = row.version
            return provider

        if "event" in self._cache and self._event_version == -1:
            return self._cache["event"]

        if "event" in self._cache:
            self._stale.append(self._cache.pop("event"))
            await self._close_stale()

        ptype, config = self._env_event_config()
        provider = self._build_event_provider(ptype, config)
        self._cache["event"] = provider
        self._event_version = -1  # env-backed sentinel
        return provider

    async def active_event_version(self, session: AsyncSession | None) -> int | None:
        row = await self._active_row(session, ProviderKind.event)
        return row.version if row else None


_manager: ProviderManager | None = None


def get_provider_manager() -> ProviderManager:
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager
