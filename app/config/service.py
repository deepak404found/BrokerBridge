from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.config_item import ConfigurationItem


class ConfigService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_items(self, *, prefix: str | None = None) -> list[ConfigurationItem]:
        result = await self.db.execute(select(ConfigurationItem).order_by(ConfigurationItem.key))
        rows = list(result.scalars().all())
        if prefix:
            rows = [r for r in rows if r.key.startswith(prefix)]
        return rows

    async def get(self, key: str) -> ConfigurationItem:
        result = await self.db.execute(select(ConfigurationItem).where(ConfigurationItem.key == key))
        item = result.scalar_one_or_none()
        if item is None:
            raise AppError("NOT_FOUND", f"Config key '{key}' not found", status_code=404)
        return item

    async def get_value(self, key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
        result = await self.db.execute(select(ConfigurationItem).where(ConfigurationItem.key == key))
        item = result.scalar_one_or_none()
        if item is None:
            return dict(default or {})
        return dict(item.value or {})

    async def put(
        self,
        key: str,
        value: dict[str, Any],
        *,
        updated_by: uuid.UUID | None = None,
    ) -> ConfigurationItem:
        result = await self.db.execute(select(ConfigurationItem).where(ConfigurationItem.key == key))
        item = result.scalar_one_or_none()
        if item is None:
            item = ConfigurationItem(key=key, value=value, version=1, updated_by=updated_by)
            self.db.add(item)
        else:
            item.value = value
            item.version = int(item.version or 1) + 1
            item.updated_by = updated_by
        await self.db.commit()
        await self.db.refresh(item)
        return item
