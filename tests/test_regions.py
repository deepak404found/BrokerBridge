import pytest


async def _auth(client):
    token = (
        await client.post(
            "/api/v1/auth/token",
            data={"username": "admin@brokerbridge.local", "password": "admin123!"},
        )
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_ips_region_filter(client):
    headers = await _auth(client)
    ewr = (
        await client.post(
            "/api/v1/infrastructure/ips",
            headers=headers,
            json={"region": "ewr"},
        )
    ).json()
    ord_ip = (
        await client.post(
            "/api/v1/infrastructure/ips",
            headers=headers,
            json={"region": "ord"},
        )
    ).json()
    listed = (await client.get("/api/v1/infrastructure/ips?region=ord", headers=headers)).json()
    ids = {row["id"] for row in listed}
    assert ord_ip["id"] in ids
    assert ewr["id"] not in ids


@pytest.mark.asyncio
async def test_routing_excludes_wrong_region_ip(client):
    headers = await _auth(client)
    brokers = (await client.get("/api/v1/brokers", headers=headers)).json()
    alpha = next(b for b in brokers if "Alpha" in b["display_name"])
    # Alpha allows ewr+ord — assign ord IP then prefer ewr → REGION_IP_MISMATCH exclude
    ip = (
        await client.post(
            "/api/v1/infrastructure/ips",
            headers=headers,
            json={"region": "ord"},
        )
    ).json()
    await client.post(
        f"/api/v1/infrastructure/ips/{ip['id']}/assign",
        headers=headers,
        json={"broker_account_id": alpha["id"]},
    )
    await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)

    preview = (
        await client.post(
            "/api/v1/monitoring/routing/preview",
            headers=headers,
            json={"client_id": alpha["client_id"], "region_preference": "ewr"},
        )
    ).json()
    excluded_ids = {str(e["broker_account_id"]) for e in preview.get("excluded", [])}
    reasons = {e["broker_account_id"]: e["reason"] for e in preview.get("excluded", [])}
    assert alpha["id"] in excluded_ids or reasons.get(alpha["id"]) == "REGION_IP_MISMATCH" or any(
        e.get("reason") == "REGION_IP_MISMATCH" for e in preview.get("excluded", [])
    )
