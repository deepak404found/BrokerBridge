from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.core.errors import AppError
from app.events.outbox import enqueue_outbox
from app.ip_manager.service import IpManagerService
from app.models.broker import BrokerAccount
from app.models.config_item import ConfigurationItem
from app.models.infrastructure import BrokerIpUsageHistory, Instance, IpAssignment, StaticIp
from app.models.order import Order
from app.providers.manager import ProviderManager
from app.whitelist.service import WhitelistService

logger = logging.getLogger("brokerbridge.rotation")

_TERMINAL_ORDER_STATUSES = frozenset({"CANCELLED", "FAILED", "FILLED", "REJECTED", "EXPIRED"})


class RotationService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        providers: ProviderManager,
    ) -> None:
        self.db = db
        self.settings = settings
        self.providers = providers
        self.ips = IpManagerService(db, settings, providers)

    async def _config_int(self, key: str, default: int) -> int:
        result = await self.db.execute(select(ConfigurationItem).where(ConfigurationItem.key == key))
        item = result.scalar_one_or_none()
        if item and isinstance(item.value, dict):
            if "seconds" in item.value:
                return int(item.value["seconds"])
            if "value" in item.value:
                return int(item.value["value"])
        return default

    async def _on_timeout_policy(self) -> str:
        result = await self.db.execute(
            select(ConfigurationItem).where(ConfigurationItem.key == "ip.rotation.on_timeout")
        )
        item = result.scalar_one_or_none()
        if item and isinstance(item.value, dict):
            return str(item.value.get("policy", "ABORT")).upper()
        return "ABORT"

    async def _cooldown_hours(self) -> int:
        result = await self.db.execute(
            select(ConfigurationItem).where(ConfigurationItem.key == "ip.reuse.cooldown_hours")
        )
        item = result.scalar_one_or_none()
        if item and isinstance(item.value, dict) and "hours" in item.value:
            return int(item.value["hours"])
        return self.settings.ip_reuse_cooldown_hours

    async def count_inflight(self, static_ip_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Order)
            .where(
                Order.static_ip_id == static_ip_id,
                Order.status.notin_(list(_TERMINAL_ORDER_STATUSES)),
            )
        )
        return int(result.scalar_one() or 0)

    async def _assert_reuse_allowed(self, broker_id: uuid.UUID, ip_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(BrokerIpUsageHistory).where(
                BrokerIpUsageHistory.broker_account_id == broker_id,
                BrokerIpUsageHistory.static_ip_id == ip_id,
            )
        )
        for hist in result.scalars().all():
            eligible = hist.reuse_eligible_at
            if eligible is not None and eligible.tzinfo is None:
                eligible = eligible.replace(tzinfo=UTC)
            if eligible and eligible > now:
                raise AppError(
                    "IP_REUSE_POLICY",
                    "Cannot reassign this IP to the same broker until cooldown elapses (BR-G04)",
                    status_code=409,
                    details={
                        "broker_account_id": str(broker_id),
                        "static_ip_id": str(ip_id),
                        "reuse_eligible_at": eligible.isoformat(),
                    },
                )

    async def _cleanup_new_ip(self, ip: StaticIp) -> None:
        infra = await self.providers.get_infrastructure_provider(self.db)
        try:
            if ip.instance_id is not None:
                await infra.detach_ip(ip.external_id)
                ip.instance_id = None
            await infra.delete_ip(ip.external_id)
        except Exception:  # noqa: BLE001
            logger.warning("rotation_cleanup_failed ip=%s", ip.id)
        ip.status = "released"

    async def rotate(
        self,
        broker_id: uuid.UUID,
        *,
        force: bool = False,
        poll_interval: float = 0.05,
    ) -> dict[str, Any]:
        lock = self.providers.get_lock_provider()
        broker_lock = f"lock:broker:{broker_id}:ip"
        token = uuid.uuid4().hex
        if not await lock.acquire(broker_lock, 60.0, token):
            raise AppError("LOCK_CONTENTION", "Broker IP lock held", status_code=409)

        new_ip: StaticIp | None = None
        activated = False
        try:
            broker_result = await self.db.execute(
                select(BrokerAccount).where(BrokerAccount.id == broker_id)
            )
            broker = broker_result.scalar_one_or_none()
            if broker is None:
                raise AppError("NOT_FOUND", "Broker not found", status_code=404)

            assign_result = await self.db.execute(
                select(IpAssignment, StaticIp)
                .join(StaticIp, IpAssignment.static_ip_id == StaticIp.id)
                .where(
                    IpAssignment.broker_account_id == broker_id,
                    IpAssignment.status == "active",
                )
            )
            row = assign_result.first()
            if row is None:
                raise AppError(
                    "NO_ACTIVE_ASSIGNMENT",
                    "Broker has no active IP assignment to rotate",
                    status_code=409,
                )
            old_assignment, old_ip = row
            region = old_ip.region
            old_instance_id = old_ip.instance_id

            # allocate commits its own TX — reload old assignment afterward
            new_ip = await self.ips.allocate_ip(region=region)
            await self._assert_reuse_allowed(broker_id, new_ip.id)

            # Refresh old rows after allocate commit
            await self.db.refresh(old_assignment)
            await self.db.refresh(old_ip)

            if old_instance_id is not None:
                inst_result = await self.db.execute(
                    select(Instance).where(Instance.id == old_instance_id)
                )
                instance = inst_result.scalar_one_or_none()
                if instance and instance.status != "destroyed":
                    new_ip = await self.ips.attach(new_ip.id, instance_id=instance.id)

            whitelist_ok = True
            try:
                wl = WhitelistService(self.db, self.settings, self.providers)
                await wl.sync(broker_id)
            except Exception as exc:  # noqa: BLE001
                whitelist_ok = False
                logger.warning("rotation_whitelist_sync_failed: %s", type(exc).__name__)

            # Re-load active assignment (still old)
            assign_result = await self.db.execute(
                select(IpAssignment).where(IpAssignment.id == old_assignment.id)
            )
            old_assignment = assign_result.scalar_one()
            old_assignment.status = "draining"
            await self.db.commit()

            drain_timeout = await self._config_int("ip.rotation.drain_timeout_seconds", 30)
            on_timeout = await self._on_timeout_policy()
            loop = asyncio.get_running_loop()
            deadline = loop.time() + max(0, drain_timeout)
            drained = False
            while True:
                inflight = await self.count_inflight(old_ip.id)
                if inflight == 0:
                    drained = True
                    break
                if loop.time() >= deadline:
                    break
                await asyncio.sleep(poll_interval)

            if not drained and not force and on_timeout != "FORCE":
                await self._cleanup_new_ip(new_ip)
                old_assignment.status = "active"
                await self.db.commit()
                raise AppError(
                    "ROTATION_DRAIN_TIMEOUT",
                    "In-flight orders did not drain before timeout; rotation aborted",
                    status_code=409,
                    details={
                        "broker_account_id": str(broker_id),
                        "old_ip_id": str(old_ip.id),
                        "inflight": await self.count_inflight(old_ip.id),
                        "drain_timeout_seconds": drain_timeout,
                        "on_timeout": on_timeout,
                        "force": force,
                    },
                )

            now = datetime.now(UTC)
            cooldown = await self._cooldown_hours()
            eligible = now + timedelta(hours=cooldown)

            old_assignment.status = "released"
            old_assignment.released_at = now
            hist = await self.db.execute(
                select(BrokerIpUsageHistory).where(
                    BrokerIpUsageHistory.broker_account_id == broker_id,
                    BrokerIpUsageHistory.static_ip_id == old_ip.id,
                    BrokerIpUsageHistory.released_at.is_(None),
                )
            )
            for h in hist.scalars().all():
                h.released_at = now
                h.reuse_eligible_at = eligible

            await self.db.refresh(old_ip)
            if old_ip.status == "attached":
                infra = await self.providers.get_infrastructure_provider(self.db)
                try:
                    await infra.detach_ip(old_ip.external_id)
                except Exception:  # noqa: BLE001
                    logger.warning("rotation_old_detach_failed")
                old_ip.instance_id = None
            old_ip.status = "released"

            new_assignment = IpAssignment(
                client_id=old_assignment.client_id,
                broker_account_id=broker_id,
                static_ip_id=new_ip.id,
                status="active",
            )
            self.db.add(new_assignment)
            self.db.add(
                BrokerIpUsageHistory(
                    broker_account_id=broker_id,
                    static_ip_id=new_ip.id,
                    used_at=now,
                )
            )

            enqueue_outbox(
                self.db,
                event_type="ip.rotated",
                topic="ip",
                payload={
                    "client_id": str(old_assignment.client_id),
                    "broker_account_id": str(broker_id),
                    "old_ip_id": str(old_ip.id),
                    "new_ip_id": str(new_ip.id),
                    "old_ip": old_ip.ip_address,
                    "new_ip": new_ip.ip_address,
                    "force": force,
                    "drained": drained,
                    "whitelist_ok": whitelist_ok,
                },
            )
            await self.db.commit()
            activated = True
            await self.db.refresh(new_assignment)
            await self.db.refresh(new_ip)

            return {
                "broker_account_id": broker_id,
                "old_ip_id": old_ip.id,
                "new_ip_id": new_ip.id,
                "old_ip": old_ip.ip_address,
                "new_ip": new_ip.ip_address,
                "old_assignment_id": old_assignment.id,
                "new_assignment_id": new_assignment.id,
                "force": force,
                "drained": drained,
                "whitelist_ok": whitelist_ok,
                "status": "rotated",
            }
        finally:
            if new_ip is not None and not activated:
                try:
                    check = await self.db.execute(
                        select(IpAssignment).where(
                            IpAssignment.static_ip_id == new_ip.id,
                            IpAssignment.status == "active",
                        )
                    )
                    if check.scalar_one_or_none() is None:
                        fresh = await self.db.execute(select(StaticIp).where(StaticIp.id == new_ip.id))
                        ip_row = fresh.scalar_one_or_none()
                        if ip_row is not None and ip_row.status != "released":
                            await self._cleanup_new_ip(ip_row)
                            await self.db.commit()
                except Exception:  # noqa: BLE001
                    logger.warning("rotation_final_cleanup_failed")
            await lock.release(broker_lock, token)
