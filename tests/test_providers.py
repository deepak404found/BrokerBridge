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
            "config": {"region": "ewr", "api_key": "super-secret"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider_type"] == "mock"
    assert body["config"]["region"] == "ewr"
    assert body["config"]["api_key"] == "***"
    assert body["validated"] is True


@pytest.mark.asyncio
async def test_activate_mock_database_backend(client):
    token = await _admin_token(client)
    r = await client.put(
        "/api/v1/admin/providers/infrastructure",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider_type": "mock",
            "validate_first": True,
            "activate": True,
            "config": {"mock_backend": "database", "default_region": "ewr"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider_type"] == "mock"
    assert body["config"]["mock_backend"] == "database"
    assert body["config"]["default_region"] == "ewr"
    assert body["validated"] is True


@pytest.mark.asyncio
async def test_activate_mock_docker_without_socket_clear_error(client):
    token = await _admin_token(client)
    r = await client.put(
        "/api/v1/admin/providers/infrastructure",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider_type": "mock",
            "validate_first": True,
            "activate": True,
            "config": {"mock_backend": "docker", "default_region": "ewr"},
        },
    )
    # Without Docker Engine / socket this must fail with actionable guidance (not opaque).
    if r.status_code == 200:
        pytest.skip("Docker Engine available — socket probe succeeded")
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "PROVIDER_VALIDATION_FAILED"
    msg = body["message"]
    assert msg != "Provider probe failed"
    assert "database" in msg.lower() or "socket" in msg.lower()
    assert body.get("details", {}).get("error") in {
        "DOCKER_UNAVAILABLE",
        "DOCKER_SDK_MISSING",
        "INFRA_UNAVAILABLE",
    }


@pytest.mark.asyncio
async def test_docker_config_falls_back_to_database_without_engine(client, monkeypatch):
    """DB may retain mock_backend=docker after restart; ops must not 500."""
    monkeypatch.setattr(
        "app.providers.manager.docker_engine_available",
        lambda _host=None: (False, "Docker socket not mounted (test)"),
    )
    token = await _admin_token(client)
    # Persist docker without probing (simulates prior activate + lost socket).
    r = await client.put(
        "/api/v1/admin/providers/infrastructure",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider_type": "mock",
            "validate_first": False,
            "activate": True,
            "config": {"mock_backend": "docker", "default_region": "ewr"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["config"]["mock_backend"] == "docker"
    assert body["degraded"] is True
    assert body["effective_backend"] == "database"
    assert body["degrade_message"]

    brokers = await client.get(
        "/api/v1/brokers?limit=5&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert brokers.status_code == 200
    client_id = brokers.json()["items"][0]["client_id"]
    inst = await client.post(
        "/api/v1/infrastructure/instances",
        headers={"Authorization": f"Bearer {token}"},
        json={"client_id": client_id, "region": "ewr", "label": "fallback-db"},
    )
    assert inst.status_code == 201, inst.text
    listed = await client.get(
        "/api/v1/infrastructure/instances",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert isinstance(listed.json(), list)


@pytest.mark.asyncio
async def test_activate_maps_eur_typo_to_ewr(client):
    token = await _admin_token(client)
    r = await client.put(
        "/api/v1/admin/providers/infrastructure",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider_type": "mock",
            "validate_first": True,
            "activate": True,
            "config": {"mock_backend": "database", "default_region": "eur"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["config"]["default_region"] == "ewr"


@pytest.mark.asyncio
async def test_activate_rejects_unknown_region(client):
    token = await _admin_token(client)
    r = await client.put(
        "/api/v1/admin/providers/infrastructure",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider_type": "mock",
            "validate_first": True,
            "activate": True,
            "config": {"mock_backend": "database", "default_region": "zzzland"},
        },
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "PROVIDER_VALIDATION_FAILED"
    assert "Unknown region" in body["message"]
    assert "ewr" in body["message"]


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
