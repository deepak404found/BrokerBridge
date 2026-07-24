import uuid

import pytest

from app.db.session import get_session_factory
from app.models.config_item import ConfigurationItem
from app.models.order import Order
from sqlalchemy import select


async def _token(client) -> str:
    r = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    assert r.status_code == 200
    return r.json()["access_token"]


async def _auth(client) -> dict:
    return {"Authorization": f"Bearer {await _token(client)}"}


async def _setup_assigned_ip(client, headers, broker_id: str, client_id: str, region: str = "ewr"):
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
async def test_rotate_happy_path(client):
    headers = await _auth(client)
    brokers = (await client.get("/api/v1/brokers", headers=headers)).json()
    alpha = next(b for b in brokers if "Alpha" in b["display_name"])
    ip = await _setup_assigned_ip(client, headers, alpha["id"], alpha["client_id"])

    r = await client.post(
        f"/api/v1/infrastructure/brokers/{alpha['id']}/rotate-ip",
        headers=headers,
        json={"force": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "rotated"
    assert body["old_ip_id"] == ip["id"]
    assert body["new_ip_id"] != ip["id"]
    assert body["old_ip"] != body["new_ip"]
    assert body["drained"] is True

    events = (await client.get("/api/v1/monitoring/events", headers=headers)).json()
    assert any(e["event_type"] == "ip.rotated" and e["status"] == "pending" for e in events)


@pytest.mark.asyncio
async def test_rotate_abort_on_drain_timeout(client):
    headers = await _auth(client)
    brokers = (await client.get("/api/v1/brokers", headers=headers)).json()
    alpha = next(b for b in brokers if "Alpha" in b["display_name"])
    ip = await _setup_assigned_ip(client, headers, alpha["id"], alpha["client_id"])

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(ConfigurationItem).where(ConfigurationItem.key == "ip.rotation.drain_timeout_seconds")
        )
        item = result.scalar_one()
        item.value = {"seconds": 0}
        session.add(
            Order(
                client_id=uuid.UUID(alpha["client_id"]),
                client_order_id=f"inflight-{uuid.uuid4().hex[:8]}",
                side="BUY",
                symbol="AAPL",
                quantity=1,
                order_type="MARKET",
                time_in_force="DAY",
                status="SUBMITTED",
                broker_account_id=uuid.UUID(alpha["id"]),
                static_ip_id=uuid.UUID(ip["id"]),
            )
        )
        await session.commit()

    r = await client.post(
        f"/api/v1/infrastructure/brokers/{alpha['id']}/rotate-ip",
        headers=headers,
        json={"force": False},
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "ROTATION_DRAIN_TIMEOUT"


@pytest.mark.asyncio
async def test_rotate_force_on_drain_timeout(client):
    headers = await _auth(client)
    brokers = (await client.get("/api/v1/brokers", headers=headers)).json()
    beta = next(b for b in brokers if "Beta" in b["display_name"])
    ip = await _setup_assigned_ip(client, headers, beta["id"], beta["client_id"])

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(ConfigurationItem).where(ConfigurationItem.key == "ip.rotation.drain_timeout_seconds")
        )
        item = result.scalar_one()
        item.value = {"seconds": 0}
        session.add(
            Order(
                client_id=uuid.UUID(beta["client_id"]),
                client_order_id=f"force-{uuid.uuid4().hex[:8]}",
                side="BUY",
                symbol="MSFT",
                quantity=1,
                order_type="MARKET",
                time_in_force="DAY",
                status="SUBMITTED",
                broker_account_id=uuid.UUID(beta["id"]),
                static_ip_id=uuid.UUID(ip["id"]),
            )
        )
        await session.commit()

    r = await client.post(
        f"/api/v1/infrastructure/brokers/{beta['id']}/rotate-ip",
        headers=headers,
        json={"force": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["force"] is True
    assert body["drained"] is False
    assert body["new_ip"] != body["old_ip"]
