"""Replay / recovery scanner for stuck orders (FR-22)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.models.order import Order, OrderAttempt
from app.orders.service import OrderService
from app.providers.manager import ProviderManager
from app.routing.engine import RoutingEngine

logger = logging.getLogger("brokerbridge.replay")

# CREATED / SUBMITTING = mid-flight; INDOUBT = explicit crash marker
STUCK_STATUSES = frozenset({"CREATED", "SUBMITTING", "INDOUBT"})
TERMINAL = frozenset({"SUBMITTED", "FAILED", "CANCELLED"})

_last_run: dict[str, Any] = {
    "ran_at": None,
    "scanned": 0,
    "retried": 0,
    "recovered": 0,
    "skipped": 0,
    "failed": 0,
}


def get_last_replay_status() -> dict[str, Any]:
    return dict(_last_run)


class ReplayService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        providers: ProviderManager,
    ) -> None:
        self.db = db
        self.settings = settings
        self.providers = providers
        self.orders = OrderService(db, settings, providers)
        self.routing = RoutingEngine(db, settings, providers)

    async def list_stuck(self, *, limit: int = 100) -> list[Order]:
        result = await self.db.execute(
            select(Order)
            .where(Order.status.in_(tuple(STUCK_STATUSES)))
            .order_by(Order.updated_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def run(self, *, limit: int = 50) -> dict[str, Any]:
        """Scan stuck orders and recover idempotently (no duplicate broker submit when possible)."""
        stuck = await self.list_stuck(limit=limit)
        scanned = len(stuck)
        retried = 0
        recovered = 0
        skipped = 0
        failed = 0
        details: list[dict[str, Any]] = []

        for order in stuck:
            try:
                outcome = await self._recover_one(order)
                details.append({"order_id": str(order.id), **outcome})
                kind = outcome.get("result")
                if kind == "recovered":
                    recovered += 1
                    retried += 1
                elif kind == "skipped":
                    skipped += 1
                elif kind == "failed":
                    failed += 1
                    retried += 1
                else:
                    skipped += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("replay_order_failed id=%s", order.id)
                failed += 1
                details.append(
                    {"order_id": str(order.id), "result": "failed", "error": str(exc)[:500]}
                )

        summary = {
            "ran_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "scanned": scanned,
            "retried": retried,
            "recovered": recovered,
            "skipped": skipped,
            "failed": failed,
            "details": details,
        }
        _last_run.clear()
        _last_run.update({k: v for k, v in summary.items() if k != "details"})
        _last_run["detail_count"] = len(details)
        return summary

    async def _recover_one(self, order: Order) -> dict[str, Any]:
        await self.db.refresh(order)
        if order.status in TERMINAL:
            return {"result": "skipped", "reason": "already_terminal", "status": order.status}

        # If any attempt already got a broker_order_id, mark SUBMITTED (idempotent recovery)
        result = await self.db.execute(
            select(OrderAttempt)
            .where(OrderAttempt.order_id == order.id)
            .order_by(OrderAttempt.attempt_no.desc())
        )
        attempts = list(result.scalars().all())
        for attempt in attempts:
            if attempt.broker_order_id and attempt.status == "submitted":
                order.status = "SUBMITTED"
                order.broker_order_id = attempt.broker_order_id
                order.broker_account_id = attempt.broker_account_id
                order.static_ip_id = attempt.static_ip_id
                order.error_code = None
                await self.db.commit()
                return {
                    "result": "recovered",
                    "reason": "adopt_existing_broker_order",
                    "status": order.status,
                    "broker_order_id": order.broker_order_id,
                }

        # Re-submit via routing (place_order uses idempotency_key per broker)
        if order.status == "INDOUBT":
            order.status = "CREATED"
            await self.db.commit()

        decision = await self.routing.select_or_raise(
            client_id=order.client_id,
            preferred_broker_id=order.preferred_broker_id,
            region_preference=order.region_preference,
            consume_rate_limit=False,
        )
        try:
            await self.orders._submit_inline(order, decision.chain)
            await self.db.refresh(order)
            if order.status == "SUBMITTED":
                return {
                    "result": "recovered",
                    "reason": "resubmit",
                    "status": order.status,
                    "broker_order_id": order.broker_order_id,
                }
            return {"result": "failed", "reason": "resubmit_non_terminal", "status": order.status}
        except Exception as exc:  # noqa: BLE001 — map to failed count
            await self.db.refresh(order)
            return {
                "result": "failed",
                "reason": str(exc)[:300],
                "status": order.status,
                "error_code": order.error_code,
            }
