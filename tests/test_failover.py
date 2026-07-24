import uuid

import pytest

from app.providers.manager import get_provider_manager
from tests.helpers import as_items


async def _login(client):
    res = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    return res.json()["access_token"]


async def _assign_ip(client, headers, broker_id, client_id, region="ewr"):
    ip = (
        await client.post(
            "/api/v1/infrastructure/ips",
            headers=headers,
            json={"region": region},
        )
    ).json()
    inst = (
        await client.post(
            "/api/v1/infrastructure/instances",
            headers=headers,
            json={"client_id": client_id, "region": region},
        )
    ).json()
    await client.post(
        f"/api/v1/infrastructure/ips/{ip['id']}/assign",
        headers=headers,
        json={"broker_account_id": broker_id},
    )
    await client.post(
        f"/api/v1/infrastructure/ips/{ip['id']}/attach",
        headers=headers,
        json={"instance_id": inst["id"]},
    )


@pytest.mark.asyncio
async def test_failover_to_second_broker(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = as_items((await client.get("/api/v1/brokers", headers=headers)).json())
    # Prefer Alpha (higher priority number in seed: Alpha=10, Beta=20) — actually
    # priority_bonus = priority * 2, so Beta (20) scores higher. Assign both IPs.
    client_id = brokers[0]["client_id"]
    alpha = next(b for b in brokers if "Alpha" in b["display_name"])
    beta = next(b for b in brokers if "Beta" in b["display_name"])
    await _assign_ip(client, headers, alpha["id"], client_id)
    await _assign_ip(client, headers, beta["id"], client_id)
    await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)

    broker = await get_provider_manager().get_broker_provider()
    broker.fail_next_n(1, status=503, code="BROKER_UNAVAILABLE")

    # Prefer Alpha so first attempt hits Alpha and fails, then Beta succeeds
    res = await client.post(
        "/api/v1/orders/buy",
        headers=headers,
        json={
            "client_id": client_id,
            "client_order_id": f"failover-{uuid.uuid4().hex[:8]}",
            "symbol": "AAPL",
            "quantity": 1,
            "order_type": "MARKET",
            "time_in_force": "DAY",
            "preferred_broker_id": alpha["id"],
            "region_preference": "ewr",
        },
    )
    assert res.status_code == 201, res.text
    order = res.json()
    assert order["status"] == "SUBMITTED"
    assert order["broker_account_id"] == beta["id"]

    failovers = await client.get("/api/v1/monitoring/failovers", headers=headers)
    assert failovers.status_code == 200
    events = as_items(failovers.json())
    assert len(events) >= 1
    assert any(
        e["from_broker_id"] == alpha["id"] and e["to_broker_id"] == beta["id"] for e in events
    )
