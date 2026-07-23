from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password
from app.config.settings import Settings
from app.models.provider_config import (
    ProviderConfig,
    ProviderKind,
    ProviderScope,
    ProviderStatus,
)
from app.models.user import User, UserRole


async def seed_defaults(session: AsyncSession, settings: Settings) -> None:
    result = await session.execute(select(User).where(User.email == settings.seed_admin_email))
    if result.scalar_one_or_none() is None:
        session.add(
            User(
                email=settings.seed_admin_email,
                role=UserRole.admin,
                password_hash=hash_password(settings.seed_admin_password),
                is_active=True,
            )
        )

    for kind, ptype in (
        (ProviderKind.infrastructure, settings.infra_provider),
        (ProviderKind.broker_default, settings.broker_provider),
    ):
        existing = await session.execute(
            select(ProviderConfig).where(
                ProviderConfig.kind == kind,
                ProviderConfig.status == ProviderStatus.active,
            )
        )
        if existing.scalars().first() is None:
            session.add(
                ProviderConfig(
                    kind=kind,
                    provider_type=ptype or "mock",
                    scope_type=ProviderScope.global_,
                    status=ProviderStatus.active,
                    version=1,
                    config_non_secret={},
                )
            )
    await session.commit()
