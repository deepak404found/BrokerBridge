"""Monitoring dashboard aggregations (FR-10 / FR-23)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.core.errors import AppError
from app.core.health_checks import run_readiness_checks
from app.events.bus_buffer import get_bus_buffer
from app.health.service import HealthService
from app.models.health import FailoverEvent
from app.models.infrastructure import StaticIp
from app.models.order import Order
from app.orders.service import OrderService
from app.providers.manager import ProviderManager
from app.rate_limit.service import RateLimitService
from app.sessions.service import SessionService
from app.sim.service import list_faults


async def build_dashboard(
    db: AsyncSession,
    settings: Settings,
    providers: ProviderManager,
) -> dict[str, Any]:
    ready = await run_readiness_checks(settings)

    sessions_rows, _ = await SessionService(db, settings, providers).list_all(limit=100, offset=0)
    session_by_status: dict[str, int] = {}
    for sess, _broker in sessions_rows:
        session_by_status[sess.status] = session_by_status.get(sess.status, 0) + 1
    sessions_total = sum(session_by_status.values())

    ip_rows = await db.execute(select(StaticIp.status, func.count()).group_by(StaticIp.status))
    ips_by_status = {row[0]: int(row[1]) for row in ip_rows.all()}
    ip_total = sum(ips_by_status.values())

    failover_count = int(
        (await db.execute(select(func.count()).select_from(FailoverEvent))).scalar_one() or 0
    )
    recent_failovers, _ = await OrderService(db, settings, providers).list_failovers(limit=5)

    engine = await OrderService(db, settings, providers).engine_stats()

    rate_rows: list[dict[str, Any]] = []
    rate_error: str | None = None
    try:
        rate_rows = await RateLimitService(db, settings, providers).list_snapshots()
    except AppError as exc:
        if exc.error_code == "REDIS_UNAVAILABLE":
            rate_error = exc.message
        else:
            raise

    health_rows = await HealthService(db, settings, providers).latest_for_brokers(probe_if_empty=False)

    bus = get_bus_buffer().stats()
    faults = [f for f in list_faults() if f.get("enabled")]

    order_total = int((await db.execute(select(func.count()).select_from(Order))).scalar_one() or 0)

    status_counts: dict[str, int] = {}
    for r in health_rows:
        st = str(r.get("status") or "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

    # Active chaos faults surface as rate-pressure signal for ops demos
    max_pressure = max((float(r.get("pressure") or 0) for r in rate_rows), default=0.0)
    if faults:
        max_pressure = max(max_pressure, 0.85 + 0.05 * min(len(faults), 3))

    return {
        "health": {
            "ready": ready.status,
            "postgres": ready.checks.postgres.model_dump(),
            "redis": ready.checks.redis.model_dump(),
            "redpanda": ready.checks.redpanda.model_dump(),
            "api": {"ok": True},
        },
        "sessions": {
            "total": sessions_total,
            "by_status": session_by_status,
        },
        "static_ips": {
            "total": ip_total,
            "by_status": ips_by_status,
        },
        "failovers": {
            "total": failover_count,
            "recent": [
                {
                    "id": str(f.id),
                    "order_id": str(f.order_id) if f.order_id else None,
                    "reason": f.reason,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in recent_failovers
            ],
        },
        "rate_limits": {
            "brokers": len(rate_rows),
            "max_pressure": max_pressure,
            "snapshots": rate_rows[:10],
            "fault_pressure": bool(faults),
            "unavailable": rate_error,
        },
        "engine": engine,
        "orders_total": order_total,
        "broker_health": {
            "count": len(health_rows),
            "statuses": status_counts,
        },
        "events": bus,
        "simulator": {"active_faults": faults},
    }
