"""Subscription lifecycle + BR-G07 expiry teardown."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.core.errors import AppError
from app.events.outbox import enqueue_outbox
from app.models.config_item import ConfigurationItem
from app.models.infrastructure import Instance
from app.models.subscription import Subscription
from app.models.user import Client
from app.providers.manager import ProviderManager

logger = logging.getLogger("brokerbridge.subscriptions")


class SubscriptionService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        providers: ProviderManager,
    ) -> None:
        self.db = db
        self.settings = settings
        self.providers = providers

    async def _default_teardown_mode(self) -> str:
        result = await self.db.execute(
            select(ConfigurationItem).where(ConfigurationItem.key == "subscription.teardown_mode")
        )
        item = result.scalar_one_or_none()
        if item and isinstance(item.value, dict):
            mode = str(item.value.get("mode") or item.value.get("policy") or "SUSPEND").upper()
            if mode in {"SUSPEND", "DESTROY"}:
                return mode
        return "SUSPEND"

    async def create(
        self,
        *,
        client_id: uuid.UUID,
        starts_at: datetime,
        ends_at: datetime,
        teardown_mode: str | None = None,
    ) -> Subscription:
        client = await self.db.get(Client, client_id)
        if client is None:
            raise AppError("NOT_FOUND", "Client not found", status_code=404)
        if ends_at <= starts_at:
            raise AppError(
                "INVALID_ARGUMENT",
                "ends_at must be after starts_at",
                status_code=422,
            )
        mode = (teardown_mode or await self._default_teardown_mode()).upper()
        if mode not in {"SUSPEND", "DESTROY"}:
            raise AppError("INVALID_ARGUMENT", "teardown_mode must be SUSPEND or DESTROY", status_code=422)
        row = Subscription(
            client_id=client_id,
            status="active",
            starts_at=starts_at,
            ends_at=ends_at,
            teardown_mode=mode,
        )
        self.db.add(row)
        # BR-G07 expiry suspends the client; a new valid window restores trading.
        now = datetime.now(UTC)
        if (
            self._as_utc(starts_at) <= now <= self._as_utc(ends_at)
            and client.status == "suspended"
        ):
            client.status = "active"
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def list(
        self, *, client_id: uuid.UUID | None = None, limit: int = 25, offset: int = 0
    ) -> tuple[list[Subscription], int]:
        from sqlalchemy import func

        filters = []
        if client_id:
            filters.append(Subscription.client_id == client_id)
        count_q = select(func.count()).select_from(Subscription)
        if filters:
            count_q = count_q.where(*filters)
        total = int((await self.db.execute(count_q)).scalar_one() or 0)
        q = select(Subscription).order_by(Subscription.ends_at.desc())
        if filters:
            q = q.where(*filters)
        q = q.limit(min(max(limit, 1), 100)).offset(max(offset, 0))
        result = await self.db.execute(q)
        return list(result.scalars().all()), total

    async def get(self, subscription_id: uuid.UUID) -> Subscription:
        row = await self.db.get(Subscription, subscription_id)
        if row is None:
            raise AppError("NOT_FOUND", "Subscription not found", status_code=404)
        return row

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _covering_active(
        self, rows: list[Subscription], *, now: datetime | None = None
    ) -> list[Subscription]:
        now = self._as_utc(now or datetime.now(UTC))
        return [
            r
            for r in rows
            if r.status == "active"
            and self._as_utc(r.starts_at) <= now <= self._as_utc(r.ends_at)
            and r.teardown_completed_at is None
        ]

    async def client_trading_allowed(self, client_id: uuid.UUID) -> bool:
        """True when client has covering ACTIVE subscription, or no subs yet (Local Lab).

        Predicate for a covering row: status=active, starts_at <= now <= ends_at,
        teardown_completed_at is null. Multiple rows: any covering row wins (EXPIRED
        siblings do not block). Client.status=suspended alone does not block when a
        covering subscription exists (renewal after BR-G07 expiry).
        """
        client = await self.db.get(Client, client_id)
        if client is None:
            return False
        result = await self.db.execute(
            select(Subscription).where(Subscription.client_id == client_id)
        )
        rows = list(result.scalars().all())
        if not rows:
            # No subscription records → Local Lab demo clients trade freely,
            # unless already suspended (e.g. leftover after all subs deleted).
            return client.status != "suspended"
        return bool(self._covering_active(rows))

    async def assert_trading_allowed(self, client_id: uuid.UUID) -> None:
        if await self.client_trading_allowed(client_id):
            client = await self.db.get(Client, client_id)
            # Clear stale BR-G07 suspend when a covering window already exists.
            if client is not None and client.status == "suspended":
                client.status = "active"
                await self.db.commit()
            return
        client = await self.db.get(Client, client_id)
        result = await self.db.execute(
            select(Subscription).where(Subscription.client_id == client_id)
        )
        rows = list(result.scalars().all())
        stale_active = [
            r
            for r in rows
            if r.status == "active" and r.teardown_completed_at is None
        ]
        hint = "Create or extend a subscription on Clients, then retry."
        if client is not None and client.status == "suspended" and not self._covering_active(rows):
            hint = (
                "Client is suspended after expiry — create a new ACTIVE subscription "
                "window on Clients to restore trading (BR-G07)."
            )
        elif stale_active:
            hint = (
                "Subscription status is active but outside starts_at/ends_at — "
                "run Enforce expiry or create a new window (BR-G07)."
            )
        raise AppError(
            "SUBSCRIPTION_EXPIRED",
            f"Client subscription expired — trading blocked (BR-G07). {hint}",
            status_code=403,
        )

    async def enforce_expiry(self, *, now: datetime | None = None) -> dict[str, int]:
        """Mark expired subscriptions, block trading, tear down infra (BR-G07)."""
        now = now or datetime.now(UTC)
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.status == "active",
                Subscription.ends_at <= now,
                Subscription.teardown_completed_at.is_(None),
            )
        )
        due = list(result.scalars().all())
        expired = 0
        torn_down = 0
        infra = await self.providers.get_infrastructure_provider(self.db)

        for sub in due:
            sub.status = "expired"
            client = await self.db.get(Client, sub.client_id)
            if client is not None:
                client.status = "suspended"

            # Tear down client instances
            inst_result = await self.db.execute(
                select(Instance).where(
                    Instance.client_id == sub.client_id,
                    Instance.status.in_(["running", "pending", "suspended"]),
                )
            )
            for inst in inst_result.scalars().all():
                try:
                    await infra.set_auto_renew(inst.external_id, False)
                    inst.auto_renew = False
                    if sub.teardown_mode == "DESTROY":
                        await infra.destroy_instance(inst.external_id)
                        inst.status = "destroyed"
                    else:
                        await infra.suspend_instance(inst.external_id)
                        inst.status = "suspended"
                    torn_down += 1
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "subscription_teardown_failed sub=%s instance=%s",
                        sub.id,
                        inst.id,
                    )

            sub.teardown_completed_at = now
            enqueue_outbox(
                self.db,
                event_type="subscription.expired",
                topic="subscriptions",
                payload={
                    "subscription_id": str(sub.id),
                    "client_id": str(sub.client_id),
                    "teardown_mode": sub.teardown_mode,
                    "ends_at": sub.ends_at.isoformat(),
                },
            )
            expired += 1

        if due:
            await self.db.commit()
        return {"expired": expired, "instances_torn_down": torn_down}

    async def expire_now(self, subscription_id: uuid.UUID) -> Subscription:
        """Force-expire a subscription for Admin/demo (sets ends_at to now then enforces)."""
        sub = await self.get(subscription_id)
        sub.ends_at = datetime.now(UTC)
        if sub.status == "active":
            await self.db.commit()
            await self.enforce_expiry()
            await self.db.refresh(sub)
        return sub
