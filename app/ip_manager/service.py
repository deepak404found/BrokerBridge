from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.core.errors import AppError
from app.models.broker import BrokerAccount
from app.models.config_item import ConfigurationItem
from app.models.infrastructure import BrokerIpUsageHistory, Instance, IpAssignment, StaticIp
from app.providers.manager import ProviderManager


class IpManagerService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        providers: ProviderManager,
    ) -> None:
        self.db = db
        self.settings = settings
        self.providers = providers

    async def _cooldown_hours(self) -> int:
        result = await self.db.execute(
            select(ConfigurationItem).where(ConfigurationItem.key == "ip.reuse.cooldown_hours")
        )
        item = result.scalar_one_or_none()
        if item and isinstance(item.value, dict) and "hours" in item.value:
            return int(item.value["hours"])
        return self.settings.ip_reuse_cooldown_hours

    async def create_instance(
        self,
        *,
        client_id: uuid.UUID,
        region: str,
        label: str | None = None,
    ) -> Instance:
        infra = await self.providers.get_infrastructure_provider(self.db)
        resource = await infra.create_instance(region, label=label)
        short = resource["external_id"].rsplit("-", 1)[-1][:8]
        display = (label or "").strip() or f"Lab Instance {region}-{short}"
        row = Instance(
            client_id=client_id,
            provider="mock",
            external_id=resource["external_id"],
            region=region,
            status=resource.get("status", "running"),
            metadata_json={"label": display},
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def destroy_instance(self, instance_id: uuid.UUID) -> None:
        result = await self.db.execute(select(Instance).where(Instance.id == instance_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError("NOT_FOUND", "Instance not found", status_code=404)
        infra = await self.providers.get_infrastructure_provider(self.db)
        await infra.destroy_instance(row.external_id)
        row.status = "destroyed"
        await self.db.commit()

    async def list_instances(self) -> list[Instance]:
        result = await self.db.execute(select(Instance).order_by(Instance.created_at.desc()))
        return list(result.scalars().all())

    async def allocate_ip(self, *, region: str) -> StaticIp:
        infra = await self.providers.get_infrastructure_provider(self.db)
        # Mock providers may collide with DB-persisted addresses after restart;
        # retry a few times before surfacing a conflict.
        last_error: Exception | None = None
        for _ in range(8):
            resource = await infra.create_ip(region)
            row = StaticIp(
                provider="mock",
                external_id=resource["external_id"],
                ip_address=resource["ip_address"],
                region=region,
                status="allocated",
                health_score=100,
                metadata_json={},
            )
            self.db.add(row)
            try:
                await self.db.commit()
                await self.db.refresh(row)
                return row
            except IntegrityError as exc:
                last_error = exc
                await self.db.rollback()
        raise AppError(
            "IP_ALLOCATE_CONFLICT",
            "Could not allocate a unique static IP address",
            status_code=409,
            details={"cause": str(last_error) if last_error else None},
        )

    async def list_ips(self) -> list[StaticIp]:
        result = await self.db.execute(select(StaticIp).order_by(StaticIp.created_at.desc()))
        return list(result.scalars().all())

    async def get_ip(self, ip_id: uuid.UUID) -> StaticIp:
        result = await self.db.execute(select(StaticIp).where(StaticIp.id == ip_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError("NOT_FOUND", "Static IP not found", status_code=404)
        return row

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

    async def assign(
        self,
        *,
        ip_id: uuid.UUID,
        broker_account_id: uuid.UUID,
        client_id: uuid.UUID | None = None,
    ) -> IpAssignment:
        lock = self.providers.get_lock_provider()
        broker_lock = f"lock:broker:{broker_account_id}:ip"
        ip_lock = f"lock:ip:{ip_id}"
        token = uuid.uuid4().hex
        if not await lock.acquire(broker_lock, 30.0, token):
            raise AppError("LOCK_CONTENTION", "Broker IP lock held", status_code=409)
        if not await lock.acquire(ip_lock, 30.0, token):
            await lock.release(broker_lock, token)
            raise AppError("LOCK_CONTENTION", "IP lock held", status_code=409)
        try:
            ip = await self.get_ip(ip_id)
            if ip.status == "quarantined":
                raise AppError("INVALID_STATE", f"IP status {ip.status} cannot be assigned", status_code=409)
            if ip.status == "attached":
                raise AppError("INVALID_STATE", "Detach IP before reassignment", status_code=409)

            broker_result = await self.db.execute(
                select(BrokerAccount).where(BrokerAccount.id == broker_account_id)
            )
            broker = broker_result.scalar_one_or_none()
            if broker is None:
                raise AppError("NOT_FOUND", "Broker not found", status_code=404)

            await self._assert_reuse_allowed(broker_account_id, ip_id)

            active = await self.db.execute(
                select(IpAssignment).where(
                    IpAssignment.broker_account_id == broker_account_id,
                    IpAssignment.status == "active",
                )
            )
            if active.scalar_one_or_none() is not None:
                raise AppError(
                    "ASSIGNMENT_CONFLICT",
                    "Broker already has an active IP assignment",
                    status_code=409,
                )

            assignment = IpAssignment(
                client_id=client_id or broker.client_id,
                broker_account_id=broker_account_id,
                static_ip_id=ip_id,
                status="active",
            )
            self.db.add(assignment)
            self.db.add(
                BrokerIpUsageHistory(
                    broker_account_id=broker_account_id,
                    static_ip_id=ip_id,
                    used_at=datetime.now(UTC),
                )
            )
            if ip.status == "released":
                ip.status = "allocated"
            await self.db.commit()
            await self.db.refresh(assignment)
            return assignment
        finally:
            await lock.release(ip_lock, token)
            await lock.release(broker_lock, token)

    async def attach(self, ip_id: uuid.UUID, *, instance_id: uuid.UUID) -> StaticIp:
        lock = self.providers.get_lock_provider()
        ip_lock = f"lock:ip:{ip_id}"
        token = uuid.uuid4().hex
        if not await lock.acquire(ip_lock, 30.0, token):
            raise AppError("LOCK_CONTENTION", "IP lock held", status_code=409)
        try:
            ip = await self.get_ip(ip_id)
            inst_result = await self.db.execute(select(Instance).where(Instance.id == instance_id))
            instance = inst_result.scalar_one_or_none()
            if instance is None:
                raise AppError("NOT_FOUND", "Instance not found", status_code=404)
            if instance.status == "destroyed":
                raise AppError("INVALID_STATE", "Instance is destroyed", status_code=409)

            infra = await self.providers.get_infrastructure_provider(self.db)
            await infra.attach_ip(ip.external_id, instance.external_id)
            ip.instance_id = instance_id
            ip.status = "attached"
            await self.db.commit()
            await self.db.refresh(ip)
            return ip
        finally:
            await lock.release(ip_lock, token)

    async def detach(self, ip_id: uuid.UUID) -> StaticIp:
        lock = self.providers.get_lock_provider()
        ip_lock = f"lock:ip:{ip_id}"
        token = uuid.uuid4().hex
        if not await lock.acquire(ip_lock, 30.0, token):
            raise AppError("LOCK_CONTENTION", "IP lock held", status_code=409)
        try:
            ip = await self.get_ip(ip_id)
            infra = await self.providers.get_infrastructure_provider(self.db)
            await infra.detach_ip(ip.external_id)
            ip.instance_id = None
            ip.status = "detached"
            await self.db.commit()
            await self.db.refresh(ip)
            return ip
        finally:
            await lock.release(ip_lock, token)

    async def release(self, ip_id: uuid.UUID) -> StaticIp:
        lock = self.providers.get_lock_provider()
        ip_lock = f"lock:ip:{ip_id}"
        token = uuid.uuid4().hex
        if not await lock.acquire(ip_lock, 30.0, token):
            raise AppError("LOCK_CONTENTION", "IP lock held", status_code=409)
        try:
            ip = await self.get_ip(ip_id)
            if ip.status == "attached":
                raise AppError("INVALID_STATE", "Detach IP before release", status_code=409)

            cooldown = await self._cooldown_hours()
            now = datetime.now(UTC)
            eligible = now + timedelta(hours=cooldown)

            result = await self.db.execute(
                select(IpAssignment).where(
                    IpAssignment.static_ip_id == ip_id,
                    IpAssignment.status == "active",
                )
            )
            for assignment in result.scalars().all():
                assignment.status = "released"
                assignment.released_at = now
                hist = await self.db.execute(
                    select(BrokerIpUsageHistory).where(
                        BrokerIpUsageHistory.broker_account_id == assignment.broker_account_id,
                        BrokerIpUsageHistory.static_ip_id == ip_id,
                        BrokerIpUsageHistory.released_at.is_(None),
                    )
                )
                for h in hist.scalars().all():
                    h.released_at = now
                    h.reuse_eligible_at = eligible

            infra = await self.providers.get_infrastructure_provider(self.db)
            await infra.delete_ip(ip.external_id)
            ip.status = "released"
            await self.db.commit()
            await self.db.refresh(ip)
            return ip
        finally:
            await lock.release(ip_lock, token)

    async def list_assignments(self) -> list[dict]:
        result = await self.db.execute(
            select(IpAssignment, StaticIp, BrokerAccount)
            .join(StaticIp, IpAssignment.static_ip_id == StaticIp.id)
            .join(BrokerAccount, IpAssignment.broker_account_id == BrokerAccount.id)
            .order_by(IpAssignment.assigned_at.desc())
        )
        rows = []
        for assignment, ip, broker in result.all():
            rows.append(
                {
                    "id": assignment.id,
                    "client_id": assignment.client_id,
                    "broker_account_id": assignment.broker_account_id,
                    "broker_display_name": broker.display_name,
                    "static_ip_id": assignment.static_ip_id,
                    "ip_address": ip.ip_address,
                    "ip_status": ip.status,
                    "region": ip.region,
                    "status": assignment.status,
                    "assigned_at": assignment.assigned_at,
                    "released_at": assignment.released_at,
                }
            )
        return rows
