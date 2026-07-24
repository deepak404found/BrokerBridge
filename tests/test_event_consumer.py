"""Wave 5 unit/integration tests — consumer, replay, monitoring, sim, pagination."""

from __future__ import annotations

import uuid

import pytest

from app.events.bus_buffer import get_bus_buffer, reset_bus_buffer_for_tests
from app.providers.memory import MemoryEventProvider
from tests.helpers import as_items


async def _login(client):
    res = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_memory_event_consumer_fanout():
    reset_bus_buffer_for_tests()
    provider = MemoryEventProvider(consumer_group="test-group")
    seen: list[tuple[str, dict]] = []

    async def handler(topic: str, event: dict) -> None:
        seen.append((topic, event))
        get_bus_buffer().append(topic=topic, event=event, source="consumed")

    await provider.subscribe(["brokerbridge.orders"], handler, consumer_group="test-group")
    assert provider.consumer_group == "test-group"
    await provider.publish("brokerbridge.orders", {"event_id": "e1", "event_type": "order.submitted", "payload": {}})
    assert len(seen) == 1
    assert get_bus_buffer().stats()["total_seen"] == 1
    await provider.aclose()


@pytest.mark.asyncio
async def test_dashboard_and_replay_and_sim(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    dash = await client.get("/api/v1/monitoring/dashboard", headers=headers)
    assert dash.status_code == 200
    body = dash.json()
    assert "health" in body and "sessions" in body and "engine" in body
    assert "events" in body

    status = await client.get("/api/v1/admin/replay/status", headers=headers)
    assert status.status_code == 200

    # Seed stuck order
    from app.db.session import get_session_factory
    from app.models.order import Order
    from decimal import Decimal

    brokers = as_items((await client.get("/api/v1/brokers", headers=headers)).json())
    client_id = brokers[0]["client_id"]
    factory = get_session_factory()
    order_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            Order(
                id=order_id,
                client_id=uuid.UUID(client_id),
                client_order_id=f"stuck-{uuid.uuid4().hex[:8]}",
                side="BUY",
                symbol="AAPL",
                quantity=Decimal("1"),
                order_type="MARKET",
                time_in_force="DAY",
                status="INDOUBT",
            )
        )
        await session.commit()

    # Need IP for recovery resubmit
    ip = (
        await client.post(
            "/api/v1/infrastructure/ips",
            headers=headers,
            json={"region": "ewr"},
        )
    ).json()
    await client.post(
        f"/api/v1/infrastructure/ips/{ip['id']}/assign",
        headers=headers,
        json={"broker_account_id": brokers[0]["id"]},
    )
    inst = (
        await client.post(
            "/api/v1/infrastructure/instances",
            headers=headers,
            json={"client_id": client_id, "region": "ewr"},
        )
    ).json()
    await client.post(
        f"/api/v1/infrastructure/ips/{ip['id']}/attach",
        headers=headers,
        json={"instance_id": inst["id"]},
    )

    run1 = await client.post("/api/v1/admin/replay/run?limit=50", headers=headers)
    assert run1.status_code == 200, run1.text
    r1 = run1.json()
    assert r1["scanned"] >= 1
    assert r1["recovered"] + r1["failed"] + r1["skipped"] >= 1

    run2 = await client.post("/api/v1/admin/replay/run?limit=50", headers=headers)
    assert run2.status_code == 200
    r2 = run2.json()
    # Second run should not re-recover the same terminal order
    assert r2["recovered"] == 0 or r2["scanned"] == 0 or r2["skipped"] >= r2["recovered"]

    faults = await client.get("/api/v1/admin/sim/faults", headers=headers)
    assert faults.status_code == 200
    assert any(f["id"] == "broker_unavailable" for f in faults.json())

    toggled = await client.post(
        "/api/v1/admin/sim/faults",
        headers=headers,
        json={"fault_id": "broker_unavailable", "enabled": True},
    )
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is True

    dash2 = await client.get("/api/v1/monitoring/dashboard", headers=headers)
    assert dash2.status_code == 200
    active = dash2.json().get("simulator", {}).get("active_faults") or []
    assert any(f.get("id") == "broker_unavailable" for f in active)
    assert float(dash2.json().get("rate_limits", {}).get("max_pressure") or 0) >= 0.85

    events = await client.get("/api/v1/monitoring/events?limit=50", headers=headers)
    assert events.status_code == 200
    ev_items = as_items(events.json())
    assert any((e.get("event_type") or "").startswith("sim.fault.") for e in ev_items)

    hist = await client.get("/api/v1/admin/sim/history?limit=10", headers=headers)
    assert hist.status_code == 200
    hist_items = as_items(hist.json())
    assert any(h.get("fault_id") == "broker_unavailable" for h in hist_items)

    cleared = await client.post("/api/v1/admin/sim/faults/clear", headers=headers)
    assert cleared.status_code == 200
    assert all(not f["enabled"] for f in cleared.json())

    dash3 = await client.get("/api/v1/monitoring/dashboard", headers=headers)
    assert dash3.status_code == 200
    assert not (dash3.json().get("simulator", {}).get("active_faults") or [])


@pytest.mark.asyncio
async def test_pagination_orders_events_ips(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    brokers = as_items((await client.get("/api/v1/brokers?limit=25&offset=0", headers=headers)).json())
    assert brokers
    client_id = brokers[0]["client_id"]

    # create a few IPs
    for _ in range(3):
        await client.post("/api/v1/infrastructure/ips", headers=headers, json={"region": "ewr"})

    ips = await client.get("/api/v1/infrastructure/ips?limit=2&offset=0", headers=headers)
    assert ips.status_code == 200
    ip_body = ips.json()
    assert "items" in ip_body and "total" in ip_body
    assert ip_body["limit"] == 2
    assert ip_body["offset"] == 0
    assert len(ip_body["items"]) <= 2
    assert ip_body["total"] >= 3
    assert ip_body["next_offset"] == 2

    page2 = await client.get("/api/v1/infrastructure/ips?limit=2&offset=2", headers=headers)
    assert page2.status_code == 200
    assert page2.json()["offset"] == 2

    # over-cap rejected by FastAPI validation
    bad = await client.get("/api/v1/orders?limit=101", headers=headers)
    assert bad.status_code == 422

    orders = await client.get(
        "/api/v1/orders",
        headers=headers,
        params={"client_id": client_id, "limit": 25, "offset": 0},
    )
    assert orders.status_code == 200
    ob = orders.json()
    assert "total" in ob and "items" in ob

    events = await client.get("/api/v1/monitoring/events?limit=25&offset=0", headers=headers)
    assert events.status_code == 200
    eb = events.json()
    assert "items" in eb and "total" in eb


@pytest.mark.asyncio
async def test_consumer_sees_drained_order_event(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = as_items((await client.get("/api/v1/brokers", headers=headers)).json())
    alpha = next(b for b in brokers if "Alpha" in b["display_name"])
    client_id = alpha["client_id"]

    ip = (
        await client.post(
            "/api/v1/infrastructure/ips", headers=headers, json={"region": "ewr"}
        )
    ).json()
    await client.post(
        f"/api/v1/infrastructure/ips/{ip['id']}/assign",
        headers=headers,
        json={"broker_account_id": alpha["id"]},
    )
    inst = (
        await client.post(
            "/api/v1/infrastructure/instances",
            headers=headers,
            json={"client_id": client_id, "region": "ewr"},
        )
    ).json()
    await client.post(
        f"/api/v1/infrastructure/ips/{ip['id']}/attach",
        headers=headers,
        json={"instance_id": inst["id"]},
    )
    await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)

    oid = f"w5-consume-{uuid.uuid4().hex[:8]}"
    buy = await client.post(
        "/api/v1/orders/buy",
        headers=headers,
        json={
            "client_id": client_id,
            "client_order_id": oid,
            "symbol": "AAPL",
            "quantity": 1,
            "region_preference": "ewr",
        },
    )
    assert buy.status_code == 201, buy.text
    await client.post("/api/v1/monitoring/events/drain", headers=headers)
    events = as_items(
        (await client.get("/api/v1/monitoring/events?source=consumed&limit=50", headers=headers)).json()
    )
    assert any(e.get("event_type") == "order.submitted" for e in events)
