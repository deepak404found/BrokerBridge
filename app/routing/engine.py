from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.service import ConfigService
from app.config.settings import Settings
from app.core.errors import AppError
from app.health.service import HealthService
from app.models.broker import BrokerAccount
from app.models.infrastructure import IpAssignment, StaticIp
from app.providers.manager import ProviderManager
from app.rate_limit.service import RateLimitService


@dataclass
class RouteCandidate:
    broker: BrokerAccount
    static_ip_id: uuid.UUID | None
    health_score: float
    health_status: str
    rate_pressure: float
    route_score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class RouteDecision:
    primary: RouteCandidate | None
    chain: list[RouteCandidate]
    excluded: list[dict[str, Any]]
    require_assigned_ip: bool


class RoutingEngine:
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
        self.health = HealthService(db, settings, providers)
        self.rate_limits = RateLimitService(db, settings, providers)

    async def _require_assigned_ip(self) -> bool:
        value = await self.config.get_value("routing.require_assigned_ip", {"enabled": True})
        return bool(value.get("enabled", True))

    async def _active_assignment(self, broker_id: uuid.UUID) -> tuple[IpAssignment, StaticIp] | None:
        result = await self.db.execute(
            select(IpAssignment, StaticIp)
            .join(StaticIp, IpAssignment.static_ip_id == StaticIp.id)
            .where(
                IpAssignment.broker_account_id == broker_id,
                IpAssignment.status == "active",
            )
        )
        row = result.first()
        if row is None:
            return None
        return row[0], row[1]

    async def select(
        self,
        *,
        client_id: uuid.UUID,
        preferred_broker_id: uuid.UUID | None = None,
        region_preference: str | None = None,
        consume_rate_limit: bool = False,
    ) -> RouteDecision:
        thresholds = await self.config.get_value(
            "routing.health_thresholds", {"healthy_min": 80, "degraded_min": 50}
        )
        degraded_min = float(thresholds.get("degraded_min", 50))
        require_ip = await self._require_assigned_ip()
        exceed_policy = await self.rate_limits.exceed_policy()

        result = await self.db.execute(
            select(BrokerAccount).where(
                BrokerAccount.client_id == client_id,
                BrokerAccount.enabled.is_(True),
            )
        )
        brokers = list(result.scalars().all())
        health_rows = {str(h["broker_account_id"]): h for h in await self.health.latest_for_brokers()}

        candidates: list[RouteCandidate] = []
        excluded: list[dict[str, Any]] = []

        for broker in brokers:
            reasons: list[str] = []
            assignment = await self._active_assignment(broker.id)
            if require_ip and assignment is None:
                excluded.append(
                    {
                        "broker_account_id": broker.id,
                        "broker_display_name": broker.display_name,
                        "reason": "NO_ASSIGNED_IP",
                    }
                )
                continue

            if region_preference:
                allowed = broker.allowed_regions or []
                if allowed and region_preference not in allowed:
                    excluded.append(
                        {
                            "broker_account_id": broker.id,
                            "broker_display_name": broker.display_name,
                            "reason": "REGION_MISMATCH",
                        }
                    )
                    continue
                if assignment and assignment[1].region != region_preference:
                    # Soft preference: still allow but note it
                    reasons.append("region_ip_mismatch")

            health = health_rows.get(str(broker.id))
            health_score = float(health["score"]) if health else 0.0
            health_status = str(health["status"]) if health else "unhealthy"
            if health_status == "unhealthy" or health_score < degraded_min:
                excluded.append(
                    {
                        "broker_account_id": broker.id,
                        "broker_display_name": broker.display_name,
                        "reason": "UNHEALTHY",
                        "score": health_score,
                    }
                )
                continue

            limit = float(broker.rate_limit_rps or 50)
            if consume_rate_limit:
                rl = await self.rate_limits.consume(broker.id, limit=limit)
            else:
                rl = await self.rate_limits.check(broker.id, limit=limit)

            rate_pressure = float(rl.get("pressure", 0.0))
            if not rl.get("allowed", True):
                if exceed_policy == "REJECT":
                    excluded.append(
                        {
                            "broker_account_id": broker.id,
                            "broker_display_name": broker.display_name,
                            "reason": "RATE_LIMITED",
                        }
                    )
                    continue
                # REROUTE / QUEUE: keep candidate but heavy pressure so others win
                rate_pressure = max(rate_pressure, 20.0)
                reasons.append("rate_limited")

            sticky = 15.0 if preferred_broker_id and broker.id == preferred_broker_id else 0.0
            if sticky:
                reasons.append("preferred_sticky")
            priority_bonus = float(broker.priority) * 2.0
            route_score = health_score + priority_bonus - rate_pressure + sticky

            candidates.append(
                RouteCandidate(
                    broker=broker,
                    static_ip_id=assignment[0].static_ip_id if assignment else None,
                    health_score=health_score,
                    health_status=health_status,
                    rate_pressure=rate_pressure,
                    route_score=route_score,
                    reasons=reasons,
                )
            )

        candidates.sort(key=lambda c: c.route_score, reverse=True)

        # Prefer sticky broker as primary when eligible
        primary: RouteCandidate | None = None
        if preferred_broker_id:
            for c in candidates:
                if c.broker.id == preferred_broker_id:
                    primary = c
                    break
        if primary is None and candidates:
            primary = candidates[0]

        chain: list[RouteCandidate] = []
        if primary:
            chain.append(primary)
            for c in candidates:
                if c.broker.id != primary.broker.id:
                    chain.append(c)

        return RouteDecision(
            primary=primary,
            chain=chain,
            excluded=excluded,
            require_assigned_ip=require_ip,
        )

    async def select_or_raise(self, **kwargs: Any) -> RouteDecision:
        decision = await self.select(**kwargs)
        if decision.primary is None:
            raise AppError(
                "NO_ROUTE",
                "No eligible broker route (check assigned IP, health, and rate limits)",
                status_code=409,
                details={
                    "excluded": [
                        {
                            "broker_account_id": str(e["broker_account_id"]),
                            "reason": e["reason"],
                        }
                        for e in decision.excluded
                    ],
                    "require_assigned_ip": decision.require_assigned_ip,
                },
            )
        return decision

    async def preview(self, **kwargs: Any) -> dict[str, Any]:
        decision = await self.select(**kwargs)
        return {
            "require_assigned_ip": decision.require_assigned_ip,
            "primary": (
                {
                    "broker_account_id": decision.primary.broker.id,
                    "broker_display_name": decision.primary.broker.display_name,
                    "route_score": decision.primary.route_score,
                    "health_score": decision.primary.health_score,
                    "health_status": decision.primary.health_status,
                    "rate_pressure": decision.primary.rate_pressure,
                    "static_ip_id": decision.primary.static_ip_id,
                    "reasons": decision.primary.reasons,
                }
                if decision.primary
                else None
            ),
            "chain": [
                {
                    "broker_account_id": c.broker.id,
                    "broker_display_name": c.broker.display_name,
                    "route_score": c.route_score,
                    "health_score": c.health_score,
                    "health_status": c.health_status,
                    "rate_pressure": c.rate_pressure,
                    "static_ip_id": c.static_ip_id,
                    "reasons": c.reasons,
                }
                for c in decision.chain
            ],
            "excluded": decision.excluded,
        }
