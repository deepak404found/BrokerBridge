import uuid

import pytest


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
    return ip, inst


@pytest.mark.asyncio
async def test_routing_requires_assigned_ip_and_sticky(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = (await client.get("/api/v1/brokers", headers=headers)).json()
    client_id = brokers[0]["client_id"]
    alpha = brokers[0]
    beta = brokers[1]

    # No IPs → NO_ROUTE / empty primary
    preview = await client.post(
        "/api/v1/monitoring/routing/preview",
        headers=headers,
        json={"client_id": client_id, "region_preference": "ewr"},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["require_assigned_ip"] is True
    assert body["primary"] is None
    assert any(e["reason"] == "NO_ASSIGNED_IP" for e in body["excluded"])

    await _assign_ip(client, headers, alpha["id"], client_id)
    await _assign_ip(client, headers, beta["id"], client_id)
    await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)

    sticky = await client.post(
        "/api/v1/monitoring/routing/preview",
        headers=headers,
        json={
            "client_id": client_id,
            "preferred_broker_id": beta["id"],
            "region_preference": "ewr",
        },
    )
    assert sticky.status_code == 200
    primary = sticky.json()["primary"]
    assert primary is not None
    assert primary["broker_account_id"] == beta["id"]
    assert "preferred_sticky" in primary["reasons"]


@pytest.mark.asyncio
async def test_admin_config_weights_roundtrip(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    got = await client.get("/api/v1/admin/config/routing.weights", headers=headers)
    assert got.status_code == 200
    assert got.json()["value"]["w_lat"] == 0.25

    put = await client.put(
        "/api/v1/admin/config/routing.weights",
        headers=headers,
        json={"value": {"w_lat": 0.2, "w_succ": 0.3, "w_conn": 0.15, "w_to": 0.25, "w_ip": 0.1}},
    )
    assert put.status_code == 200
    assert put.json()["value"]["w_lat"] == 0.2
    assert put.json()["version"] >= 2
