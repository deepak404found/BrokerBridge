import pytest
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.provider_config import ProviderConfig, ProviderStatus
from app.models.user import User


@pytest.mark.asyncio
async def test_seeded_admin_and_providers(client):
    factory = get_session_factory()
    async with factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        providers = (
            await session.execute(
                select(ProviderConfig).where(ProviderConfig.status == ProviderStatus.active)
            )
        ).scalars().all()
    assert any(u.email == "admin@brokerbridge.local" for u in users)
    kinds = {p.kind.value for p in providers}
    assert "infrastructure" in kinds
    assert "broker_default" in kinds
