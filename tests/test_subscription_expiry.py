"""Subscription expiry teardown (BR-G07)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.db.session import get_session_factory
from app.models.infrastructure import Instance
from app.models.user import Client
from app.providers.manager import get_provider_manager
from app.subscriptions.service import SubscriptionService
from sqlalchemy import select


async def _admin_token(client) -> str:
    r = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_expiry_blocks_orders_and_suspends(client):
    token = await _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    brokers = await client.get("/api/v1/brokers?limit=5&offset=0", headers=headers)
    broker = brokers.json()["items"][0]
    client_id = broker["client_id"]

    # Provision instance for client
    inst = await client.post(
        "/api/v1/infrastructure/instances",
        headers=headers,
        json={"client_id": client_id, "region": "ewr", "label": "expiry-lab"},
    )
    assert inst.status_code == 201
    instance_id = inst.json()["id"]

    # Assign IP so orders work before expiry
    ip = await client.post(
        "/api/v1/infrastructure/ips",
        headers=headers,
        json={"region": "ewr"},
    )
    ip_id = ip.json()["id"]
    await client.post(
        f"/api/v1/infrastructure/ips/{ip_id}/assign",
        headers=headers,
        json={"broker_account_id": broker["id"]},
    )
    await client.post(
        f"/api/v1/infrastructure/ips/{ip_id}/attach",
        headers=headers,
        json={"instance_id": instance_id},
    )

    starts = datetime.now(UTC) - timedelta(days=2)
    ends = datetime.now(UTC) - timedelta(hours=1)
    sub = await client.post(
        "/api/v1/subscriptions",
        headers=headers,
        json={
            "client_id": client_id,
            "starts_at": starts.isoformat(),
            "ends_at": ends.isoformat(),
            "teardown_mode": "SUSPEND",
        },
    )
    assert sub.status_code == 201
    sub_id = sub.json()["id"]

    enforced = await client.post("/api/v1/subscriptions/enforce-expiry", headers=headers)
    assert enforced.status_code == 200
    assert enforced.json()["expired"] >= 1

    got = await client.get(f"/api/v1/subscriptions/{sub_id}", headers=headers)
    assert got.json()["status"] == "expired"
    assert got.json()["teardown_completed_at"] is not None

    factory = get_session_factory()
    async with factory() as session:
        row = await session.get(Instance, __import__("uuid").UUID(instance_id))
        assert row is not None
        assert row.auto_renew is False
        assert row.status == "suspended"
        client_row = await session.get(Client, __import__("uuid").UUID(client_id))
        assert client_row is not None
        assert client_row.status == "suspended"

    order = await client.post(
        "/api/v1/orders/buy",
        headers=headers,
        json={
            "client_id": client_id,
            "client_order_id": f"expiry-{datetime.now(UTC).timestamp()}",
            "symbol": "AAPL",
            "quantity": 1,
            "region_preference": "ewr",
        },
    )
    assert order.status_code == 403
    assert order.json()["error_code"] == "SUBSCRIPTION_EXPIRED"


@pytest.mark.asyncio
async def test_no_subscription_allows_trading(configured_app):
    factory = get_session_factory()
    manager = get_provider_manager()
    async with factory() as session:
        from app.config.settings import get_settings

        svc = SubscriptionService(session, get_settings(), manager)
        result = await session.execute(select(Client).limit(1))
        client = result.scalar_one()
        assert await svc.client_trading_allowed(client.id) is True


@pytest.mark.asyncio
async def test_new_subscription_restores_trading_after_expiry(client):
    """ACTIVE coverage after expiry must unblock trading (client was suspended by BR-G07)."""
    token = await _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    brokers = await client.get("/api/v1/brokers?limit=5&offset=0", headers=headers)
    broker = brokers.json()["items"][0]
    client_id = broker["client_id"]

    past_starts = datetime.now(UTC) - timedelta(days=2)
    past_ends = datetime.now(UTC) - timedelta(hours=1)
    expired = await client.post(
        "/api/v1/subscriptions",
        headers=headers,
        json={
            "client_id": client_id,
            "starts_at": past_starts.isoformat(),
            "ends_at": past_ends.isoformat(),
            "teardown_mode": "SUSPEND",
        },
    )
    assert expired.status_code == 201
    await client.post("/api/v1/subscriptions/enforce-expiry", headers=headers)

    factory = get_session_factory()
    async with factory() as session:
        client_row = await session.get(Client, __import__("uuid").UUID(client_id))
        assert client_row is not None
        assert client_row.status == "suspended"

    now = datetime.now(UTC)
    renewed = await client.post(
        "/api/v1/subscriptions",
        headers=headers,
        json={
            "client_id": client_id,
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(days=7)).isoformat(),
            "teardown_mode": "SUSPEND",
        },
    )
    assert renewed.status_code == 201
    assert renewed.json()["status"] == "active"

    async with factory() as session:
        client_row = await session.get(Client, __import__("uuid").UUID(client_id))
        assert client_row is not None
        assert client_row.status == "active"
        from app.config.settings import get_settings

        svc = SubscriptionService(session, get_settings(), get_provider_manager())
        assert await svc.client_trading_allowed(client_row.id) is True
