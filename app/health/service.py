from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.service import ConfigService
from app.config.settings import Settings
from app.models.broker import BrokerAccount
from app.models.health import HealthSnapshot
from app.models.infrastructure import IpAssignment, StaticIp
from app.providers.manager import ProviderManager


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_health_score(
    *,
    latency_ms: float,
    success_rate: float,
    timeout_rate: float,
    connectivity: bool,
    ip_health: float,
    weights: dict[str, float],
    latency_budget_ms: float,
) -> float:
    latency_score = clamp(100.0 * (1.0 - float(latency_ms) / float(latency_budget_ms)), 0.0, 100.0)
    success_score = float(success_rate) * 100.0
    connectivity_score = 100.0 if connectivity else 0.0
    timeout_penalty = float(timeout_rate) * 100.0
    ip_score = float(ip_health)
    w_lat = float(weights.get("w_lat", 0.25))
    w_succ = float(weights.get("w_succ", 0.30))
    w_conn = float(weights.get("w_conn", 0.15))
    w_to = float(weights.get("w_to", 0.20))
    w_ip = float(weights.get("w_ip", 0.10))
    return (
        w_lat * latency_score
        + w_succ * success_score
        + w_conn * connectivity_score
        + w_to * (100.0 - timeout_penalty)
        + w_ip * ip_score
    )


def status_from_score(score: float, thresholds: dict[str, Any]) -> str:
    healthy_min = float(thresholds.get("healthy_min", 80))
    degraded_min = float(thresholds.get("degraded_min", 50))
    if score >= healthy_min:
        return "healthy"
    if score >= degraded_min:
        return "degraded"
    return "unhealthy"


class HealthService:
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

    async def _ip_health_for_broker(self, broker_id: uuid.UUID) -> float:
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
            return 50.0
        _, ip = row
        if ip.health_score is not None:
            return float(ip.health_score)
        return 100.0

    async def probe_broker(self, broker: BrokerAccount) -> HealthSnapshot:
        weights = await self.config.get_value(
            "routing.weights",
            {"w_lat": 0.25, "w_succ": 0.30, "w_conn": 0.15, "w_to": 0.20, "w_ip": 0.10},
        )
        thresholds = await self.config.get_value(
            "routing.health_thresholds", {"healthy_min": 80, "degraded_min": 50}
        )
        broker_provider = await self.providers.get_broker_provider(self.db)
        started = time.perf_counter()
        connectivity = True
        success_rate = 1.0
        timeout_rate = 0.0
        try:
            probe = await broker_provider.probe()
            latency_ms = (time.perf_counter() - started) * 1000.0
            connectivity = bool(probe.get("ok", True))
            success_rate = float(probe.get("success_rate", 1.0 if connectivity else 0.0))
            timeout_rate = float(probe.get("timeout_rate", 0.0 if connectivity else 1.0))
        except Exception:
            latency_ms = (time.perf_counter() - started) * 1000.0
            connectivity = False
            success_rate = 0.0
            timeout_rate = 1.0

        ip_health = await self._ip_health_for_broker(broker.id)
        score = compute_health_score(
            latency_ms=latency_ms,
            success_rate=success_rate,
            timeout_rate=timeout_rate,
            connectivity=connectivity,
            ip_health=ip_health,
            weights=weights,
            latency_budget_ms=self.settings.latency_budget_ms,
        )
        status = status_from_score(score, thresholds)
        snap = HealthSnapshot(
            broker_account_id=broker.id,
            latency_ms=Decimal(str(round(latency_ms, 4))),
            success_rate=Decimal(str(round(success_rate, 6))),
            timeout_rate=Decimal(str(round(timeout_rate, 6))),
            connectivity=connectivity,
            ip_health=Decimal(str(round(ip_health, 4))),
            score=Decimal(str(round(score, 4))),
            status=status,
            measured_at=datetime.now(UTC),
        )
        self.db.add(snap)
        await self.db.commit()
        await self.db.refresh(snap)
        return snap

    async def probe_all(self) -> list[HealthSnapshot]:
        result = await self.db.execute(select(BrokerAccount).where(BrokerAccount.enabled.is_(True)))
        brokers = list(result.scalars().all())
        snaps: list[HealthSnapshot] = []
        for broker in brokers:
            snaps.append(await self.probe_broker(broker))
        return snaps

    async def latest_for_brokers(self, *, probe_if_empty: bool = True) -> list[dict[str, Any]]:
        result = await self.db.execute(select(BrokerAccount).order_by(BrokerAccount.priority.asc()))
        brokers = list(result.scalars().all())
        out: list[dict[str, Any]] = []
        for broker in brokers:
            snap_result = await self.db.execute(
                select(HealthSnapshot)
                .where(HealthSnapshot.broker_account_id == broker.id)
                .order_by(HealthSnapshot.measured_at.desc())
                .limit(1)
            )
            snap = snap_result.scalar_one_or_none()
            if snap is None and probe_if_empty and broker.enabled:
                snap = await self.probe_broker(broker)
            if snap is None:
                continue
            out.append(
                {
                    "broker_account_id": broker.id,
                    "broker_display_name": broker.display_name,
                    "enabled": broker.enabled,
                    "latency_ms": float(snap.latency_ms or 0),
                    "success_rate": float(snap.success_rate or 0),
                    "timeout_rate": float(snap.timeout_rate or 0),
                    "connectivity": bool(snap.connectivity),
                    "ip_health": float(snap.ip_health or 0),
                    "score": float(snap.score),
                    "status": snap.status,
                    "measured_at": snap.measured_at,
                    "breakdown": {
                        "latency_ms": float(snap.latency_ms or 0),
                        "success_rate": float(snap.success_rate or 0),
                        "timeout_rate": float(snap.timeout_rate or 0),
                        "connectivity": bool(snap.connectivity),
                        "ip_health": float(snap.ip_health or 0),
                    },
                }
            )
        return out
