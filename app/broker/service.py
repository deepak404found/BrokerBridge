from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.core.crypto import encrypt_secret
from app.core.errors import AppError
from app.models.broker import BrokerAccount
from app.providers.manager import ProviderManager


class BrokerService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        providers: ProviderManager,
    ) -> None:
        self.db = db
        self.settings = settings
        self.providers = providers

    async def create(
        self,
        *,
        client_id: uuid.UUID,
        provider_type: str,
        display_name: str,
        credentials: dict[str, Any],
        priority: int = 100,
        allowed_regions: list[str] | None = None,
        rate_limit_rps: Decimal | float | None = None,
        enabled: bool = True,
    ) -> BrokerAccount:
        encrypted = encrypt_secret(json.dumps(credentials), self.settings)
        broker_provider = await self.providers.get_broker_provider(self.db)
        caps = await broker_provider.list_capabilities()
        row = BrokerAccount(
            client_id=client_id,
            provider_type=provider_type,
            display_name=display_name,
            priority=priority,
            enabled=enabled,
            allowed_regions=allowed_regions or ["ewr"],
            capabilities=caps,
            credentials_encrypted=encrypted,
            rate_limit_rps=Decimal(str(rate_limit_rps)) if rate_limit_rps is not None else None,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def list(self, *, client_id: uuid.UUID | None = None, limit: int = 25, offset: int = 0) -> tuple[list[BrokerAccount], int]:
        filters = []
        if client_id is not None:
            filters.append(BrokerAccount.client_id == client_id)
        count_q = select(func.count()).select_from(BrokerAccount)
        if filters:
            count_q = count_q.where(*filters)
        total = int((await self.db.execute(count_q)).scalar_one() or 0)
        stmt = select(BrokerAccount).order_by(BrokerAccount.priority.asc(), BrokerAccount.display_name)
        if filters:
            stmt = stmt.where(*filters)
        stmt = stmt.limit(min(max(limit, 1), 100)).offset(max(offset, 0))
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def get(self, broker_id: uuid.UUID) -> BrokerAccount:
        result = await self.db.execute(select(BrokerAccount).where(BrokerAccount.id == broker_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise AppError("NOT_FOUND", f"Broker {broker_id} not found", status_code=404)
        return row

    async def patch(
        self,
        broker_id: uuid.UUID,
        *,
        enabled: bool | None = None,
        priority: int | None = None,
        display_name: str | None = None,
        rate_limit_rps: Decimal | float | None = None,
        allowed_regions: list[str] | None = None,
    ) -> BrokerAccount:
        row = await self.get(broker_id)
        if enabled is not None:
            row.enabled = enabled
        if priority is not None:
            row.priority = priority
        if display_name is not None:
            row.display_name = display_name
        if rate_limit_rps is not None:
            row.rate_limit_rps = Decimal(str(rate_limit_rps))
        if allowed_regions is not None:
            row.allowed_regions = allowed_regions
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def refresh_capabilities(self, broker_id: uuid.UUID) -> BrokerAccount:
        row = await self.get(broker_id)
        broker = await self.providers.get_broker_provider(self.db)
        row.capabilities = await broker.list_capabilities()
        await self.db.commit()
        await self.db.refresh(row)
        return row
