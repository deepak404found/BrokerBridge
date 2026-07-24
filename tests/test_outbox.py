import pytest

from app.db.session import get_session_factory
from app.events.outbox import drain_outbox, enqueue_outbox
from app.providers.manager import get_provider_manager
from app.providers.memory import MemoryEventProvider


async def _token(client) -> str:
    r = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_outbox_drain_publishes_to_memory(client):
    factory = get_session_factory()
    manager = get_provider_manager()
    async with factory() as session:
        enqueue_outbox(
            session,
            event_type="order.submitted",
            topic="orders",
            payload={"order_id": "demo"},
        )
        await session.commit()
        stats = await drain_outbox(session, manager, limit=10)
    assert stats["sent"] >= 1
    provider = await manager.get_event_provider()
    assert isinstance(provider, MemoryEventProvider)
    assert any(t.endswith("orders") or "orders" in t for t, _ in provider.published)
    assert any(e.get("event_type") == "order.submitted" for _, e in provider.published)


@pytest.mark.asyncio
async def test_order_place_enqueues_outbox(client):
    token = await _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = (await client.get("/api/v1/brokers", headers=headers)).json()
    alpha = next(b for b in brokers if "Alpha" in b["display_name"])
    # ensure IP
    ip = (
        await client.post(
            "/api/v1/infrastructure/ips",
            headers=headers,
            json={"region": "ewr"},
        )
    ).json()
    inst = (
        await client.post(
            "/api/v1/infrastructure/instances",
            headers=headers,
            json={"client_id": alpha["client_id"], "region": "ewr"},
        )
    ).json()
    await client.post(
        f"/api/v1/infrastructure/ips/{ip['id']}/assign",
        headers=headers,
        json={"broker_account_id": alpha["id"]},
    )
    await client.post(
        f"/api/v1/infrastructure/ips/{ip['id']}/attach",
        headers=headers,
        json={"instance_id": inst["id"]},
    )
    await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)

    r = await client.post(
        "/api/v1/orders/buy",
        headers=headers,
        json={
            "client_id": alpha["client_id"],
            "client_order_id": "outbox-buy-1",
            "symbol": "AAPL",
            "quantity": 1,
            "region_preference": "ewr",
        },
    )
    assert r.status_code == 201, r.text
    events = (await client.get("/api/v1/monitoring/events", headers=headers)).json()
    assert any(e["event_type"] == "order.submitted" for e in events)
