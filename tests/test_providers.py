import pytest

from app.db.session import get_session_factory
from app.providers.broker.mock import MockBrokerProvider
from app.providers.infrastructure.mock import MockInfrastructureProvider
from app.providers.manager import get_provider_manager


async def _admin_token(client) -> str:
    r = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_list_providers_seeded(client):
    token = await _admin_token(client)
    r = await client.get(
        "/api/v1/admin/providers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    kinds = {row["kind"] for row in r.json()}
    assert "infrastructure" in kinds
    assert "broker_default" in kinds


@pytest.mark.asyncio
async def test_activate_mock_masks_secrets(client):
    token = await _admin_token(client)
    r = await client.put(
        "/api/v1/admin/providers/infrastructure",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider_type": "mock",
            "validate_first": True,
            "activate": True,
            "config": {"region": "nyc", "api_key": "super-secret"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider_type"] == "mock"
    assert body["config"]["region"] == "nyc"
    assert body["config"]["api_key"] == "***"
    assert body["validated"] is True


@pytest.mark.asyncio
async def test_activate_unsupported_provider_fails(client):
    token = await _admin_token(client)
    r = await client.put(
        "/api/v1/admin/providers/broker_default",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider_type": "real-broker-x",
            "validate_first": True,
            "activate": True,
            "config": {},
        },
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "PROVIDER_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_provider_manager_resolves_mocks(client):
    # lifespan seeds DB; resolve via manager
    factory = get_session_factory()
    manager = get_provider_manager()
    async with factory() as session:
        infra = await manager.get_infrastructure_provider(session)
        broker = await manager.get_broker_provider(session)
    assert isinstance(infra, MockInfrastructureProvider)
    assert isinstance(broker, MockBrokerProvider)
    probe = await infra.probe()
    assert probe.get("ok") is True
