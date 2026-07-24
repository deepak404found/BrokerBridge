import pytest


async def _login(client):
    res = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_ip_lifecycle_and_reuse_policy(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = (await client.get("/api/v1/brokers", headers=headers)).json()
    broker_id = brokers[0]["id"]
    client_id = brokers[0]["client_id"]

    inst = await client.post(
        "/api/v1/infrastructure/instances",
        headers=headers,
        json={"client_id": client_id, "region": "ewr"},
    )
    assert inst.status_code == 201
    inst_body = inst.json()
    instance_id = inst_body["id"]
    assert inst_body["display_name"]
    assert "ewr" in inst_body["display_name"]
    listed = (await client.get("/api/v1/infrastructure/instances", headers=headers)).json()
    match = next(i for i in listed if i["id"] == instance_id)
    assert match["display_name"] == inst_body["display_name"]

    allocated = await client.post(
        "/api/v1/infrastructure/ips",
        headers=headers,
        json={"region": "ewr"},
    )
    assert allocated.status_code == 201
    ip = allocated.json()
    assert ip["ip_address"].startswith(("198.51.100.", "203.0.113."))
    ip_id = ip["id"]

    assigned = await client.post(
        f"/api/v1/infrastructure/ips/{ip_id}/assign",
        headers=headers,
        json={"broker_account_id": broker_id},
    )
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "active"

    attached = await client.post(
        f"/api/v1/infrastructure/ips/{ip_id}/attach",
        headers=headers,
        json={"instance_id": instance_id},
    )
    assert attached.status_code == 200
    assert attached.json()["status"] == "attached"

    detached = await client.post(f"/api/v1/infrastructure/ips/{ip_id}/detach", headers=headers)
    assert detached.status_code == 200
    assert detached.json()["status"] == "detached"

    released = await client.delete(f"/api/v1/infrastructure/ips/{ip_id}", headers=headers)
    assert released.status_code == 200
    assert released.json()["status"] == "released"

    reuse = await client.post(
        f"/api/v1/infrastructure/ips/{ip_id}/assign",
        headers=headers,
        json={"broker_account_id": broker_id},
    )
    assert reuse.status_code == 409
    assert reuse.json()["error_code"] == "IP_REUSE_POLICY"


@pytest.mark.asyncio
async def test_concurrent_assign_second_fails(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = (await client.get("/api/v1/brokers", headers=headers)).json()
    broker_id = brokers[0]["id"]

    ip1 = (
        await client.post("/api/v1/infrastructure/ips", headers=headers, json={"region": "ewr"})
    ).json()
    ip2 = (
        await client.post("/api/v1/infrastructure/ips", headers=headers, json={"region": "ewr"})
    ).json()

    first = await client.post(
        f"/api/v1/infrastructure/ips/{ip1['id']}/assign",
        headers=headers,
        json={"broker_account_id": broker_id},
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/v1/infrastructure/ips/{ip2['id']}/assign",
        headers=headers,
        json={"broker_account_id": broker_id},
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "ASSIGNMENT_CONFLICT"
