import pytest

import app.providers.manager as provider_manager
from app.config.settings import get_settings
from app.db.session import get_session_factory
from app.providers.manager import get_provider_manager
from app.providers.memory import MemoryEventProvider


@pytest.mark.asyncio
async def test_event_resolution_env_memory(client):
    manager = get_provider_manager()
    provider = await manager.get_event_provider(None)
    assert isinstance(provider, MemoryEventProvider)


@pytest.mark.asyncio
async def test_event_db_active_overrides_env(client, monkeypatch):
    token = (
        await client.post(
            "/api/v1/auth/token",
            data={"username": "admin@brokerbridge.local", "password": "admin123!"},
        )
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    monkeypatch.setenv("EVENT_PROVIDER", "redpanda_local")
    monkeypatch.setenv("REDPANDA_BROKERS", "should-not-use:9092")
    get_settings.cache_clear()
    provider_manager._manager = None

    # Activate memory via Admin — DB wins over env
    r = await client.put(
        "/api/v1/admin/providers/event",
        headers=headers,
        json={
            "provider_type": "memory",
            "validate_first": True,
            "activate": True,
            "config": {},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["provider_type"] == "memory"

    factory = get_session_factory()
    manager = get_provider_manager()
    async with factory() as session:
        provider = await manager.get_event_provider(session)
    assert isinstance(provider, MemoryEventProvider)
    assert manager._event_version == r.json()["version"]


@pytest.mark.asyncio
async def test_event_invalidate_rebuilds_provider(client):
    manager = get_provider_manager()
    p1 = await manager.get_event_provider(None)
    assert isinstance(p1, MemoryEventProvider)
    await p1.publish("t", {"x": 1})
    manager.invalidate("event")
    p2 = await manager.get_event_provider(None)
    assert isinstance(p2, MemoryEventProvider)
    assert p1 is not p2
    assert p1.closed is True
    assert p2.published == []


@pytest.mark.asyncio
async def test_activate_event_masks_secrets(client):
    token = (
        await client.post(
            "/api/v1/auth/token",
            data={"username": "admin@brokerbridge.local", "password": "admin123!"},
        )
    ).json()["access_token"]
    r = await client.put(
        "/api/v1/admin/providers/event",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "provider_type": "memory",
            "validate_first": True,
            "activate": True,
            "config": {"topic_prefix": "lab", "username": "u", "password": "secret"},
        },
    )
    assert r.status_code == 200
    cfg = r.json()["config"]
    assert cfg["topic_prefix"] == "lab"
    assert cfg["username"] == "***"
    assert cfg["password"] == "***"
