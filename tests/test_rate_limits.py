import pytest

from app.providers.memory import MemoryRateLimit


@pytest.mark.asyncio
async def test_memory_rate_limit_consume_and_pressure():
    rl = MemoryRateLimit()
    key = "rl:broker:test"
    for _ in range(3):
        snap = await rl.consume(key, limit=3, window_seconds=60)
        assert snap["allowed"] is True
    denied = await rl.consume(key, limit=3, window_seconds=60)
    assert denied["allowed"] is False
    assert denied["remaining"] == 0
    assert denied["pressure"] == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_rate_limits_monitoring_api(client):
    token = (
        await client.post(
            "/api/v1/auth/token",
            data={"username": "admin@brokerbridge.local", "password": "admin123!"},
        )
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    res = await client.get("/api/v1/monitoring/rate-limits", headers=headers)
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) >= 2
    assert all("remaining" in r and "pressure" in r for r in rows)
