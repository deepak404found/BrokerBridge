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
from app.providers.infrastructure.docker_util import (
    DOCKER_SOCKET_HINT,
    docker_engine_available,
)
from app.providers.infrastructure.mock import MockInfrastructureProvider
from app.providers.infrastructure.vultr import VultrProvider
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
        self._infra_version: int | None = None
        self._stale: list[Any] = []
        # When configured mock_backend=docker but Engine/socket unavailable.
        self._infra_degraded: dict[str, Any] | None = None

    def invalidate(self, kind: str | None = None) -> None:
        if kind is None:
            for key, provider in list(self._cache.items()):
                if key == "event":
                    self._stale.append(provider)
            self._cache.clear()
            self._event_version = None
            self._infra_version = None
            self._infra_degraded = None
            return
        if kind == "event":
            old = self._cache.pop("event", None)
            if old is not None:
                self._stale.append(old)
            self._event_version = None
            return
        # Map API kind names onto cache keys
        cache_key = {"broker_default": "broker", "infrastructure": "infrastructure"}.get(kind, kind)
        self._cache.pop(cache_key, None)
        if kind != cache_key:
            self._cache.pop(kind, None)
        if cache_key == "infrastructure" or kind == "infrastructure":
            self._infra_version = None
            self._infra_degraded = None

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

            # Short timeouts so Local Lab chaos (compose stop redis) fails fast
            # instead of hanging Admin/dashboard requests.
            self._redis = from_url(
                self.settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
            )
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

    async def _load_infra_secrets(self, row: ProviderConfig) -> dict[str, Any]:
        public = dict(row.config_non_secret or {})
        if not row.config_encrypted:
            return public
        try:
            raw = decrypt_secret(row.config_encrypted, self.settings)
            secrets = json.loads(raw) if raw else {}
            if isinstance(secrets, dict):
                public.update(secrets)
        except Exception:  # noqa: BLE001
            logger.warning("infra_config_decrypt_failed version=%s", row.version)
        return public

    def _resolve_mock_backend(self, config: dict[str, Any] | None = None) -> str:
        cfg = config or {}
        backend = (
            str(cfg.get("mock_backend") or "").strip().lower()
            or (self.settings.mock_infra_backend or "").strip().lower()
            or "database"
        )
        if backend not in {"database", "docker"}:
            backend = "database"
        return backend

    def _build_mock_infra(
        self,
        backend: str,
        *,
        allow_docker_fallback: bool = True,
    ) -> MockInfrastructureProvider:
        docker_host = (self.settings.docker_host or "").strip() or None
        resolved = backend
        self._infra_degraded = None
        if resolved == "docker" and allow_docker_fallback:
            ok, err = docker_engine_available(docker_host)
            if not ok:
                msg = err or DOCKER_SOCKET_HINT
                logger.warning(
                    "mock_docker_unavailable falling_back=database hint=%s",
                    msg,
                )
                self._infra_degraded = {
                    "configured_backend": "docker",
                    "effective_backend": "database",
                    "message": msg,
                }
                resolved = "database"

        session_factory = None
        if resolved == "database":
            try:
                from app.db.session import get_session_factory

                session_factory = get_session_factory()
            except Exception:  # noqa: BLE001
                session_factory = None
        return MockInfrastructureProvider(
            backend=resolved,
            session_factory=session_factory,
            docker_host=docker_host,
        )

    def _build_vultr(self, config: dict[str, Any]) -> VultrProvider:
        api_key = str(config.get("api_key") or self.settings.vultr_api_key or "").strip()
        region = str(
            config.get("default_region")
            or config.get("region")
            or self.settings.vultr_default_region
            or "ewr"
        ).strip()
        return VultrProvider(api_key=api_key, default_region=region)

    async def get_infrastructure_provider(self, session: AsyncSession | None = None) -> Any:
        row = await self._active_row(session, ProviderKind.infrastructure)
        if row is not None:
            if "infrastructure" in self._cache and self._infra_version == row.version:
                return self._cache["infrastructure"]
            config = await self._load_infra_secrets(row)
            ptype = (row.provider_type or "mock").strip().lower()
            if ptype == "vultr":
                provider: Any = self._build_vultr(config)
            else:
                backend = self._resolve_mock_backend(config)
                provider = self._build_mock_infra(backend)
            self._cache["infrastructure"] = provider
            self._infra_version = row.version
            return provider

        if "infrastructure" in self._cache and self._infra_version == -1:
            return self._cache["infrastructure"]

        ptype = (self.settings.infra_provider or "mock").strip().lower()
        if ptype == "vultr":
            provider = self._build_vultr(
                {
                    "api_key": self.settings.vultr_api_key,
                    "default_region": self.settings.vultr_default_region,
                }
            )
        else:
            provider = self._build_mock_infra(self._resolve_mock_backend())
        self._cache["infrastructure"] = provider
        self._infra_version = -1
        return provider

    async def describe_infrastructure(self, session: AsyncSession | None = None) -> dict[str, Any]:
        """Admin/status helper: active type + mock backend without exposing secrets."""
        row = await self._active_row(session, ProviderKind.infrastructure)
        provider = await self.get_infrastructure_provider(session)
        ptype = row.provider_type if row else (self.settings.infra_provider or "mock")
        version = row.version if row else None
        effective = getattr(provider, "backend_name", None)
        configured = effective
        if row is not None and str(ptype).lower() == "mock":
            configured = self._resolve_mock_backend(dict(row.config_non_secret or {}))
        elif str(ptype).lower() == "mock":
            configured = self._resolve_mock_backend()
        degraded = self._infra_degraded
        return {
            "provider_type": ptype,
            "version": version,
            "backend": effective,
            "configured_backend": configured,
            "effective_backend": effective,
            "degraded": bool(degraded),
            "degrade_message": (degraded or {}).get("message"),
            "label": (
                f"mock ({effective})"
                if str(ptype).lower() == "mock" and effective
                else str(ptype)
            ),
        }

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
        consumer_group = (
            config.get("consumer_group")
            or self.settings.kafka_consumer_group
            or "brokerbridge-lab"
        )
        if ptype == "memory":
            provider = MemoryEventProvider(consumer_group=str(consumer_group))
            provider.topic_prefix = config.get("topic_prefix") or self.settings.kafka_topic_prefix
            topic_map = config.get("topic_map") if isinstance(config.get("topic_map"), dict) else None
            provider.topic_map = topic_map
            return provider

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
            return MemoryEventProvider(consumer_group=str(consumer_group))

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
            consumer_group=str(consumer_group),
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
