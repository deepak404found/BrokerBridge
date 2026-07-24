"""Chaos simulator faults must change mock provider behavior (not only logs)."""

import pytest
from tests.helpers import as_items

from app.providers.broker.mock import MockBrokerError, MockBrokerProvider
from app.providers.infrastructure.mock import MockInfrastructureError, MockInfrastructureProvider
from app.providers.manager import get_provider_manager
from app.sim.service import clear_all_faults, set_fault


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
async def test_mock_broker_reject_and_unavailable_unit(configured_app):
    mgr = get_provider_manager()
    broker = await mgr.get_broker_provider()
    assert isinstance(broker, MockBrokerProvider)

    await set_fault("broker_reject", enabled=True, providers=mgr)
    probe = await broker.probe()
    assert probe.get("ok") is False
    with pytest.raises(MockBrokerError) as rej:
        await broker.place_order({"symbol": "AAPL"})
    assert rej.value.code == "BROKER_REJECT"
    assert rej.value.retryable is False

    await set_fault("broker_unavailable", enabled=True, providers=mgr)
    probe2 = await broker.probe()
    assert probe2.get("ok") is False
    with pytest.raises(MockBrokerError) as unavail:
        await broker.place_order({"symbol": "AAPL"})
    assert unavail.value.code == "BROKER_UNAVAILABLE"
    assert unavail.value.retryable is True

    await clear_all_faults(mgr)
    ok = await broker.probe()
    assert ok.get("ok") is True
    accepted = await broker.place_order({"symbol": "AAPL"})
    assert accepted.get("status") == "accepted"


@pytest.mark.asyncio
async def test_mock_infra_probe_fail_unit(configured_app):
    mgr = get_provider_manager()
    infra = await mgr.get_infrastructure_provider()
    assert isinstance(infra, MockInfrastructureProvider)

    await set_fault("infra_probe_fail", enabled=True, providers=mgr)
    probe = await infra.probe()
    assert probe.get("ok") is False
    assert probe.get("error") == "INFRA_UNAVAILABLE"
    with pytest.raises(MockInfrastructureError) as exc:
        await infra.create_ip("ewr")
    assert exc.value.code == "INFRA_UNAVAILABLE"

    await clear_all_faults(mgr)
    ok = await infra.probe()
    assert ok.get("ok") is True
    created = await infra.create_ip("ewr")
    assert created.get("ip_address")


@pytest.mark.asyncio
async def test_faults_survive_provider_cache_invalidate(configured_app):
    mgr = get_provider_manager()
    await set_fault("broker_reject", enabled=True, providers=mgr)
    mgr.invalidate("broker")
    broker = await mgr.get_broker_provider()
    with pytest.raises(MockBrokerError) as rej:
        await broker.place_order({"symbol": "MSFT"})
    assert rej.value.code == "BROKER_REJECT"
    await clear_all_faults(mgr)


@pytest.mark.asyncio
async def test_api_broker_reject_fails_order_and_degrades_health(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = as_items((await client.get("/api/v1/brokers", headers=headers)).json())
    client_id = brokers[0]["client_id"]
    await _assign_ip(client, headers, brokers[0]["id"], client_id)
    await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)

    toggled = await client.post(
        "/api/v1/admin/sim/faults",
        headers=headers,
        json={"fault_id": "broker_reject", "enabled": True},
    )
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is True

    buy = await client.post(
        "/api/v1/orders/buy",
        headers=headers,
        json={
            "client_id": client_id,
            "client_order_id": "fault-reject-1",
            "symbol": "AAPL",
            "quantity": 1,
            "order_type": "MARKET",
            "time_in_force": "DAY",
        },
    )
    assert buy.status_code == 400
    assert buy.json()["error_code"] == "BROKER_REJECT"

    probed = await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)
    assert probed.status_code == 200
    health_rows = probed.json()
    assert isinstance(health_rows, list)
    assert any(
        (h.get("status") in {"degraded", "unhealthy"} or float(h.get("score") or 100) < 80)
        for h in health_rows
    )

    dash = await client.get("/api/v1/monitoring/dashboard", headers=headers)
    assert dash.status_code == 200
    assert any(f.get("id") == "broker_reject" for f in (dash.json().get("simulator", {}).get("active_faults") or []))
    statuses = dash.json().get("broker_health", {}).get("statuses") or {}
    assert (statuses.get("unhealthy") or 0) + (statuses.get("degraded") or 0) >= 1

    cleared = await client.post("/api/v1/admin/sim/faults/clear", headers=headers)
    assert cleared.status_code == 200
    await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)

    buy2 = await client.post(
        "/api/v1/orders/buy",
        headers=headers,
        json={
            "client_id": client_id,
            "client_order_id": "fault-reject-recover",
            "symbol": "AAPL",
            "quantity": 1,
            "order_type": "MARKET",
            "time_in_force": "DAY",
        },
    )
    assert buy2.status_code == 201
    assert buy2.json()["status"] == "SUBMITTED"


@pytest.mark.asyncio
async def test_api_infra_probe_fail_blocks_allocate(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    toggled = await client.post(
        "/api/v1/admin/sim/faults",
        headers=headers,
        json={"fault_id": "infra_probe_fail", "enabled": True},
    )
    assert toggled.status_code == 200

    alloc = await client.post(
        "/api/v1/infrastructure/ips",
        headers=headers,
        json={"region": "ewr"},
    )
    assert alloc.status_code in {502, 503, 409, 400}
    body = alloc.json()
    assert body.get("error_code") in {"INFRA_UNAVAILABLE", "PROVIDER_ERROR", "IP_ALLOCATE_CONFLICT"}

    await client.post("/api/v1/admin/sim/faults/clear", headers=headers)
    ok = await client.post(
        "/api/v1/infrastructure/ips",
        headers=headers,
        json={"region": "ewr"},
    )
    assert ok.status_code == 201
