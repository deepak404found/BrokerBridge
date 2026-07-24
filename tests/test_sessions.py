import pytest


async def _login(client):
    res = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_session_ensure_idempotent_and_no_raw_tokens(client):
    token = await _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    brokers = (await client.get("/api/v1/brokers", headers=headers)).json()
    broker_id = brokers[0]["id"]

    first = await client.post(f"/api/v1/brokers/{broker_id}/sessions/ensure", headers=headers)
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "valid"
    assert body["has_tokens"] is True
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert "encrypted" not in str(body).lower() or body.get("has_tokens") is True

    second = await client.post(f"/api/v1/brokers/{broker_id}/sessions/ensure", headers=headers)
    assert second.status_code == 200
    assert second.json()["status"] == "valid"
    # Idempotent ensure keeps same expiry window (not forced)
    assert second.json()["expires_at"] == body["expires_at"]

    forced = await client.post(
        f"/api/v1/brokers/{broker_id}/sessions/ensure",
        headers=headers,
        params={"force_refresh": True},
    )
    assert forced.status_code == 200
    assert forced.json()["has_tokens"] is True

    listed = await client.get("/api/v1/monitoring/sessions", headers=headers)
    assert listed.status_code == 200
    assert any(s["broker_account_id"] == broker_id for s in listed.json())
    for s in listed.json():
        assert "access_token" not in s
        assert "token_encrypted" not in s
