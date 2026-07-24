import uuid

import pytest
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
    return ip


@pytest.mark.asyncio
async def test_order_blocked_without_assigned_ip(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = as_items((await client.get("/api/v1/brokers", headers=headers)).json())
    client_id = brokers[0]["client_id"]
    res = await client.post(
        "/api/v1/orders/buy",
        headers=headers,
        json={
            "client_id": client_id,
            "client_order_id": "no-ip-1",
            "symbol": "AAPL",
            "quantity": 1,
            "order_type": "MARKET",
            "time_in_force": "DAY",
        },
    )
    assert res.status_code == 409
    assert res.json()["error_code"] == "NO_ROUTE"


@pytest.mark.asyncio
async def test_buy_idempotent_and_cancel(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = as_items((await client.get("/api/v1/brokers", headers=headers)).json())
    client_id = brokers[0]["client_id"]
    await _assign_ip(client, headers, brokers[0]["id"], client_id)
    await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)

    body = {
        "client_id": client_id,
        "client_order_id": "idem-buy-1",
        "symbol": "AAPL",
        "quantity": 5,
        "order_type": "MARKET",
        "time_in_force": "DAY",
        "region_preference": "ewr",
    }
    first = await client.post("/api/v1/orders/buy", headers=headers, json=body)
    assert first.status_code == 201
    order = first.json()
    assert order["status"] == "SUBMITTED"
    assert order["broker_order_id"]

    second = await client.post("/api/v1/orders/buy", headers=headers, json=body)
    assert second.status_code == 200
    assert second.json()["id"] == order["id"]

    cancel = await client.post(f"/api/v1/orders/{order['id']}/cancel", headers=headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"

    listed = await client.get("/api/v1/orders", headers=headers, params={"client_id": client_id})
    assert listed.status_code == 200
    assert any(i["id"] == order["id"] for i in listed.json()["items"])


@pytest.mark.asyncio
async def test_sell_and_engine_stats(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = as_items((await client.get("/api/v1/brokers", headers=headers)).json())
    client_id = brokers[0]["client_id"]
    await _assign_ip(client, headers, brokers[0]["id"], client_id)
    await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)

    sell = await client.post(
        "/api/v1/orders/sell",
        headers=headers,
        json={
            "client_id": client_id,
            "client_order_id": f"sell-{uuid.uuid4().hex[:8]}",
            "symbol": "MSFT",
            "quantity": 2,
            "order_type": "MARKET",
            "time_in_force": "DAY",
        },
    )
    assert sell.status_code == 201
    assert sell.json()["side"] == "SELL"

    engine = await client.get("/api/v1/monitoring/orders/engine", headers=headers)
    assert engine.status_code == 200
    assert engine.json()["execution_mode"] == "inline"
    assert "by_status" in engine.json()
