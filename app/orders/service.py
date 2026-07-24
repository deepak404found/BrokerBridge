from __future__ import annotations

import asyncio
import hashlib
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.service import ConfigService
from app.config.settings import Settings
from app.core.errors import AppError
from app.models.health import FailoverEvent
from app.models.order import Order, OrderAttempt
from app.providers.broker.mock import MockBrokerError
from app.providers.manager import ProviderManager
from app.routing.engine import RoutingEngine
from app.sessions.service import SessionService


_inflight_sem: asyncio.Semaphore | None = None
_inflight_count = 0


def get_inflight_semaphore(max_inflight: int) -> asyncio.Semaphore:
    global _inflight_sem
    if _inflight_sem is None:
        _inflight_sem = asyncio.Semaphore(max_inflight)
    return _inflight_sem


def reset_inflight_for_tests() -> None:
    global _inflight_sem, _inflight_count
    _inflight_sem = None
    _inflight_count = 0


class OrderService:
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
        self.routing = RoutingEngine(db, settings, providers)
        self.sessions = SessionService(db, settings, providers)

    async def _execution_mode(self) -> str:
        value = await self.config.get_value("orders.execution_mode", {"mode": "inline"})
        return str(value.get("mode", "inline")).lower()

    def _idem_key(self, client_id: uuid.UUID, client_order_id: str, broker_id: uuid.UUID) -> str:
        raw = f"{client_id}:{client_order_id}:{broker_id}"
        return hashlib.sha256(raw.encode()).hexdigest()[:64]

    async def get(self, order_id: uuid.UUID) -> Order:
        result = await self.db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if order is None:
            raise AppError("NOT_FOUND", "Order not found", status_code=404)
        return order

    async def list_orders(
        self,
        *,
        client_id: uuid.UUID | None = None,
        status: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Order]:
        q = select(Order).order_by(Order.created_at.desc())
        if client_id:
            q = q.where(Order.client_id == client_id)
        if status:
            q = q.where(Order.status == status)
        if symbol:
            q = q.where(Order.symbol == symbol)
        q = q.limit(min(limit, 200)).offset(max(offset, 0))
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def engine_stats(self) -> dict[str, Any]:
        global _inflight_count
        result = await self.db.execute(select(Order.status, func.count()).group_by(Order.status))
        by_status = {row[0]: int(row[1]) for row in result.all()}
        return {
            "inflight": _inflight_count,
            "max_inflight": self.settings.max_inflight_orders,
            "by_status": by_status,
            "execution_mode": await self._execution_mode(),
        }

    async def list_failovers(self, *, limit: int = 50) -> list[FailoverEvent]:
        result = await self.db.execute(
            select(FailoverEvent).order_by(FailoverEvent.created_at.desc()).limit(min(limit, 200))
        )
        return list(result.scalars().all())

    async def place(
        self,
        *,
        client_id: uuid.UUID,
        client_order_id: str,
        side: str,
        symbol: str,
        quantity: Decimal | float | str,
        order_type: str = "MARKET",
        time_in_force: str = "DAY",
        preferred_broker_id: uuid.UUID | None = None,
        region_preference: str | None = None,
    ) -> tuple[Order, bool]:
        """Place an order. Returns (order, created). created=False means idempotent replay."""
        existing = await self.db.execute(
            select(Order).where(
                Order.client_id == client_id,
                Order.client_order_id == client_order_id,
            )
        )
        prior = existing.scalar_one_or_none()
        if prior is not None:
            return prior, False

        mode = await self._execution_mode()
        if mode != "inline":
            raise AppError(
                "UNSUPPORTED_MODE",
                f"Order execution mode '{mode}' is not available in this wave (inline only)",
                status_code=501,
            )

        sem = get_inflight_semaphore(self.settings.max_inflight_orders)
        acquired = False
        try:
            try:
                await asyncio.wait_for(sem.acquire(), timeout=0.05)
                acquired = True
            except TimeoutError as exc:
                raise AppError(
                    "QUEUE_FULL",
                    "Order engine saturated — try again shortly",
                    status_code=503,
                ) from exc

            global _inflight_count
            _inflight_count += 1
            try:
                order = Order(
                    client_id=client_id,
                    client_order_id=client_order_id,
                    side=side.upper(),
                    symbol=symbol.upper(),
                    quantity=Decimal(str(quantity)),
                    order_type=order_type.upper(),
                    time_in_force=time_in_force.upper(),
                    status="CREATED",
                    preferred_broker_id=preferred_broker_id,
                    region_preference=region_preference,
                )
                self.db.add(order)
                try:
                    await self.db.commit()
                    await self.db.refresh(order)
                except IntegrityError:
                    await self.db.rollback()
                    again = await self.db.execute(
                        select(Order).where(
                            Order.client_id == client_id,
                            Order.client_order_id == client_order_id,
                        )
                    )
                    prior = again.scalar_one_or_none()
                    if prior is not None:
                        return prior, False
                    raise

                decision = await self.routing.select_or_raise(
                    client_id=client_id,
                    preferred_broker_id=preferred_broker_id,
                    region_preference=region_preference,
                    consume_rate_limit=False,
                )

                await self._submit_inline(order, decision.chain)
                await self.db.refresh(order)
                return order, True
            finally:
                _inflight_count = max(0, _inflight_count - 1)
        finally:
            if acquired:
                sem.release()

    async def _submit_inline(self, order: Order, chain: list) -> None:
        broker_provider = await self.providers.get_broker_provider(self.db)
        last_error: str | None = None
        last_code: str | None = None

        for idx, candidate in enumerate(chain):
            # Skip rate-limited brokers when REROUTE — try consume; if denied, skip to next
            from app.rate_limit.service import RateLimitService

            rl_svc = RateLimitService(self.db, self.settings, self.providers)
            rl = await rl_svc.consume(candidate.broker.id, limit=float(candidate.broker.rate_limit_rps or 50))
            if not rl.get("allowed", True):
                policy = await rl_svc.exceed_policy()
                if policy == "REJECT":
                    order.status = "FAILED"
                    order.error_code = "RATE_LIMITED"
                    await self.db.commit()
                    raise AppError("RATE_LIMITED", "Broker rate limit exceeded", status_code=429)
                # REROUTE: try next
                last_error = "rate limited"
                last_code = "RATE_LIMITED"
                if idx + 1 < len(chain):
                    self.db.add(
                        FailoverEvent(
                            order_id=order.id,
                            from_broker_id=candidate.broker.id,
                            to_broker_id=chain[idx + 1].broker.id,
                            reason="RATE_LIMITED",
                            details={"policy": policy},
                        )
                    )
                    await self.db.commit()
                continue

            await self.sessions.ensure(candidate.broker.id)

            attempt_no = idx + 1
            idem = self._idem_key(order.client_id, order.client_order_id, candidate.broker.id)
            payload = {
                "client_order_id": order.client_order_id,
                "side": order.side,
                "symbol": order.symbol,
                "quantity": str(order.quantity),
                "order_type": order.order_type,
                "time_in_force": order.time_in_force,
                "broker_account_id": str(candidate.broker.id),
                "static_ip_id": str(candidate.static_ip_id) if candidate.static_ip_id else None,
            }
            attempt = OrderAttempt(
                order_id=order.id,
                attempt_no=attempt_no,
                broker_account_id=candidate.broker.id,
                static_ip_id=candidate.static_ip_id,
                status="submitting",
                request_payload=payload,
                idempotency_key=idem,
            )
            self.db.add(attempt)
            order.status = "SUBMITTING"
            order.broker_account_id = candidate.broker.id
            order.static_ip_id = candidate.static_ip_id
            await self.db.commit()
            await self.db.refresh(attempt)

            try:
                result = await broker_provider.place_order(payload)
                attempt.status = "submitted"
                attempt.response_payload = result
                attempt.broker_order_id = result.get("broker_order_id")
                order.status = "SUBMITTED"
                order.broker_order_id = attempt.broker_order_id
                order.error_code = None
                await self.db.commit()
                return
            except MockBrokerError as exc:
                attempt.status = "failed"
                attempt.error = exc.message
                attempt.response_payload = {"code": exc.code, "status": exc.status}
                await self.db.commit()
                last_error = exc.message
                last_code = exc.code
                if not exc.retryable:
                    order.status = "FAILED"
                    order.error_code = exc.code
                    await self.db.commit()
                    raise AppError(exc.code, exc.message, status_code=400) from exc
                if idx + 1 < len(chain):
                    self.db.add(
                        FailoverEvent(
                            order_id=order.id,
                            from_broker_id=candidate.broker.id,
                            to_broker_id=chain[idx + 1].broker.id,
                            reason=exc.code,
                            details={"message": exc.message, "status": exc.status},
                        )
                    )
                    await self.db.commit()
                    continue
            except Exception as exc:  # noqa: BLE001 — map unknown broker failures
                attempt.status = "failed"
                attempt.error = str(exc)
                await self.db.commit()
                last_error = str(exc)
                last_code = "BROKER_ERROR"
                if idx + 1 < len(chain):
                    self.db.add(
                        FailoverEvent(
                            order_id=order.id,
                            from_broker_id=candidate.broker.id,
                            to_broker_id=chain[idx + 1].broker.id,
                            reason="BROKER_ERROR",
                            details={"message": str(exc)},
                        )
                    )
                    await self.db.commit()
                    continue

        order.status = "FAILED"
        order.error_code = last_code or "FAILOVER_EXHAUSTED"
        await self.db.commit()
        raise AppError(
            "FAILOVER_EXHAUSTED",
            last_error or "All brokers in failover chain failed",
            status_code=502,
            details={"order_id": str(order.id), "error_code": order.error_code},
        )

    async def cancel(self, order_id: uuid.UUID) -> Order:
        order = await self.get(order_id)
        if order.status in {"CANCELLED", "FAILED"}:
            raise AppError(
                "ORDER_NOT_CANCELABLE",
                f"Order status {order.status} cannot be cancelled",
                status_code=409,
            )
        if order.status not in {"SUBMITTED", "SUBMITTING", "CREATED"}:
            raise AppError(
                "ORDER_NOT_CANCELABLE",
                f"Order status {order.status} cannot be cancelled",
                status_code=409,
            )
        if not order.broker_order_id:
            # Never reached broker — mark cancelled locally
            order.status = "CANCELLED"
            await self.db.commit()
            await self.db.refresh(order)
            return order

        broker_provider = await self.providers.get_broker_provider(self.db)
        try:
            await broker_provider.cancel_order(
                order.broker_order_id,
                payload={"order_id": str(order.id), "client_order_id": order.client_order_id},
            )
        except MockBrokerError as exc:
            raise AppError(
                "ORDER_NOT_CANCELABLE",
                exc.message,
                status_code=409,
            ) from exc

        order.status = "CANCELLED"
        await self.db.commit()
        await self.db.refresh(order)
        return order
