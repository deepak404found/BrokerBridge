import pytest


async def _login(client):
    res = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_brokers_crud_and_capabilities(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    listed = await client.get("/api/v1/brokers", headers=headers)
    assert listed.status_code == 200
    seed = listed.json()
    assert len(seed) >= 2
    client_id = seed[0]["client_id"]

    created = await client.post(
        "/api/v1/brokers",
        headers=headers,
        json={
            "client_id": client_id,
            "provider_type": "mock",
            "display_name": "Test Broker W2",
            "priority": 99,
            "credentials": {"api_key": "k", "api_secret": "s"},
            "allowed_regions": ["ewr"],
            "rate_limit_rps": 12,
        },
    )
    assert created.status_code == 201
    broker = created.json()
    assert broker["display_name"] == "Test Broker W2"
    assert "credentials" not in broker
    assert broker["capabilities"].get("supports_whitelist") is True

    detail = await client.get(f"/api/v1/brokers/{broker['id']}", headers=headers)
    assert detail.status_code == 200

    patched = await client.patch(
        f"/api/v1/brokers/{broker['id']}",
        headers=headers,
        json={"enabled": False},
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    refreshed = await client.post(
        f"/api/v1/brokers/{broker['id']}/capabilities/refresh",
        headers=headers,
    )
    assert refreshed.status_code == 200
    assert "asset_classes" in refreshed.json()["capabilities"]

    reenabled = await client.patch(
        f"/api/v1/brokers/{broker['id']}",
        headers=headers,
        json={"enabled": True},
    )
    assert reenabled.json()["enabled"] is True


@pytest.mark.asyncio
async def test_brokers_auth_required(client):
    res = await client.get("/api/v1/brokers")
    assert res.status_code == 401
    assert res.json()["error_code"] == "UNAUTHORIZED"
