from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.service import ConfigService
from app.config.settings import Settings
from app.core.errors import AppError
from app.core.redis_deps import raise_redis_unavailable
from app.models.broker import BrokerAccount
from app.providers.errors import RedisUnavailableError
from app.providers.manager import ProviderManager


class RateLimitService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        providers: ProviderManager,
    ) -> None:
        self.db = db
        self.settings = settings
        self.providers = providers
        self.config = ConfigService(db)

    def _key(self, broker_id: uuid.UUID) -> str:
        return f"rl:broker:{broker_id}"

    async def exceed_policy(self) -> str:
        value = await self.config.get_value("rate_limit.exceed_policy", {"policy": "REROUTE"})
        return str(value.get("policy", "REROUTE")).upper()

    async def snapshot_for_broker(self, broker: BrokerAccount) -> dict[str, Any]:
        limit = float(broker.rate_limit_rps or 50)
        rl = self.providers.get_rate_limit_provider()
        try:
            snap = await rl.check(self._key(broker.id), limit=limit, window_seconds=1.0)
        except RedisUnavailableError as exc:
            raise_redis_unavailable(exc, op="rate limits")
        return {
            "broker_account_id": broker.id,
            "broker_display_name": broker.display_name,
            "limit_rps": limit,
            "used": snap["used"],
            "remaining": snap["remaining"],
            "pressure": snap["pressure"],
            "window_seconds": snap["window_seconds"],
        }

    async def list_snapshots(self) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(BrokerAccount).order_by(BrokerAccount.priority.asc())
        )
        out: list[dict[str, Any]] = []
        for broker in result.scalars().all():
            out.append(await self.snapshot_for_broker(broker))
        return out

    async def check(self, broker_id: uuid.UUID, *, limit: float | None = None) -> dict[str, Any]:
        if limit is None:
            result = await self.db.execute(select(BrokerAccount).where(BrokerAccount.id == broker_id))
            broker = result.scalar_one_or_none()
            if broker is None:
                raise AppError("NOT_FOUND", "Broker not found", status_code=404)
            limit = float(broker.rate_limit_rps or 50)
        rl = self.providers.get_rate_limit_provider()
        try:
            return await rl.check(self._key(broker_id), limit=float(limit), window_seconds=1.0)
        except RedisUnavailableError as exc:
            raise_redis_unavailable(exc, op="rate limits")

    async def consume(self, broker_id: uuid.UUID, *, limit: float | None = None) -> dict[str, Any]:
        if limit is None:
            result = await self.db.execute(select(BrokerAccount).where(BrokerAccount.id == broker_id))
            broker = result.scalar_one_or_none()
            if broker is None:
                raise AppError("NOT_FOUND", "Broker not found", status_code=404)
            limit = float(broker.rate_limit_rps or 50)
        rl = self.providers.get_rate_limit_provider()
        try:
            return await rl.consume(self._key(broker_id), limit=float(limit), window_seconds=1.0)
        except RedisUnavailableError as exc:
            raise_redis_unavailable(exc, op="rate limits")

    async def pressure(self, broker_id: uuid.UUID, *, limit: float | None = None) -> float:
        snap = await self.check(broker_id, limit=limit)
        return float(snap.get("pressure", 0.0))
