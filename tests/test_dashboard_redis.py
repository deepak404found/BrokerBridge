"""Dashboard degrades cleanly when Redis-backed rate limits fail."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.errors import AppError
from app.schemas.health import CheckResult, ReadyChecks, ReadyResponse


@pytest.mark.asyncio
async def test_dashboard_survives_redis_rate_limit_outage(client):
    headers = {"Authorization": f"Bearer {(await _token(client))}"}
    ok = CheckResult(status="ok", latency_ms=1.0, detail=None)
    fail = CheckResult(status="fail", latency_ms=5.0, detail="ConnectionRefusedError")
    fake_ready = ReadyResponse(
        status="not_ready",
        checks=ReadyChecks(postgres=ok, redis=fail, redpanda=ok),
    )
    redis_err = AppError(
        "REDIS_UNAVAILABLE",
        "Redis dependency is down (rate limits)",
        status_code=503,
        details={"dependency": "redis"},
    )
    with (
        patch(
            "app.monitoring.service.run_readiness_checks",
            new=AsyncMock(return_value=fake_ready),
        ),
        patch(
            "app.monitoring.service.RateLimitService.list_snapshots",
            new=AsyncMock(side_effect=redis_err),
        ),
    ):
        res = await client.get("/api/v1/monitoring/dashboard", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["health"]["ready"] == "not_ready"
    assert body["health"]["redis"]["status"] == "fail"
    assert body["rate_limits"]["unavailable"]
    assert body["rate_limits"]["brokers"] == 0


@pytest.mark.asyncio
async def test_rate_limits_api_maps_redis_down(client):
    from app.providers.errors import RedisUnavailableError

    headers = {"Authorization": f"Bearer {(await _token(client))}"}

    class BrokenRl:
        async def check(self, *args, **kwargs):
            raise RedisUnavailableError("Redis unavailable", detail="ConnectionError")

    with patch(
        "app.providers.manager.ProviderManager.get_rate_limit_provider",
        return_value=BrokenRl(),
    ):
        res = await client.get("/api/v1/monitoring/rate-limits", headers=headers)
    assert res.status_code == 503
    body = res.json()
    assert body["error_code"] == "REDIS_UNAVAILABLE"


async def _token(client) -> str:
    res = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    assert res.status_code == 200
    return res.json()["access_token"]
