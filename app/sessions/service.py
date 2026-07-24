from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.errors import AppError
from app.models.broker import BrokerAccount, BrokerSession
from app.providers.manager import ProviderManager


class SessionService:
    def __init__(
        self,
        db: AsyncSession,
        settings: Settings,
        providers: ProviderManager,
    ) -> None:
        self.db = db
        self.settings = settings
        self.providers = providers

    async def get_for_broker(self, broker_id: uuid.UUID) -> BrokerSession | None:
        result = await self.db.execute(
            select(BrokerSession).where(BrokerSession.broker_account_id == broker_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[tuple[BrokerSession, BrokerAccount]]:
        result = await self.db.execute(
            select(BrokerSession, BrokerAccount).join(
                BrokerAccount, BrokerSession.broker_account_id == BrokerAccount.id
            )
        )
        return list(result.all())

    async def ensure(self, broker_id: uuid.UUID, *, force_refresh: bool = False) -> BrokerSession:
        result = await self.db.execute(select(BrokerAccount).where(BrokerAccount.id == broker_id))
        broker = result.scalar_one_or_none()
        if broker is None:
            raise AppError("NOT_FOUND", f"Broker {broker_id} not found", status_code=404)
        if not broker.enabled:
            raise AppError("BROKER_DISABLED", "Broker is disabled", status_code=409)

        lock = self.providers.get_lock_provider()
        session_cache = self.providers.get_session_provider()
        lock_key = f"lock:session:{broker_id}"
        token = uuid.uuid4().hex
        acquired = await lock.acquire(lock_key, 30.0, token)
        if not acquired:
            raise AppError("LOCK_CONTENTION", "Session refresh already in progress", status_code=409)

        try:
            existing = await self.get_for_broker(broker_id)
            now = datetime.now(UTC)
            expires = existing.expires_at if existing else None
            if expires is not None and expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if (
                existing
                and not force_refresh
                and existing.status == "valid"
                and expires
                and expires > now
            ):
                return existing

            broker_provider = await self.providers.get_broker_provider(self.db)
            if existing and existing.refresh_token_encrypted and not force_refresh:
                refresh = decrypt_secret(existing.refresh_token_encrypted, self.settings)
                tokens = await broker_provider.refresh_session(refresh)
            else:
                creds = json.loads(decrypt_secret(broker.credentials_encrypted, self.settings))
                tokens = await broker_provider.authenticate(creds)

            expires_raw = tokens.get("expires_at")
            expires_at = (
                datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
                if isinstance(expires_raw, str)
                else now
            )
            access_enc = encrypt_secret(tokens["access_token"], self.settings)
            refresh_enc = encrypt_secret(tokens.get("refresh_token") or "", self.settings)

            if existing is None:
                existing = BrokerSession(broker_account_id=broker_id)
                self.db.add(existing)

            existing.access_token_encrypted = access_enc
            existing.refresh_token_encrypted = refresh_enc
            existing.expires_at = expires_at
            existing.status = tokens.get("status") or "valid"
            await self.db.commit()
            await self.db.refresh(existing)

            await session_cache.set(
                f"session:{broker_id}",
                {
                    "broker_id": str(broker_id),
                    "status": existing.status,
                    "expires_at": expires_at.isoformat(),
                },
                ttl_seconds=3600,
            )
            return existing
        finally:
            await lock.release(lock_key, token)
