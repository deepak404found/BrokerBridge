from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.health import CheckResult, ReadyChecks, ReadyResponse


@pytest.mark.asyncio
async def test_live(client):
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert "X-Request-ID" in r.headers


@pytest.mark.asyncio
async def test_live_echoes_client_request_id(client):
    r = await client.get("/health/live", headers={"X-Request-ID": "req-test-1"})
    assert r.status_code == 200
    assert r.headers["X-Request-ID"] == "req-test-1"


@pytest.mark.asyncio
async def test_ready_ok_when_checks_pass(client):
    ok = CheckResult(status="ok", latency_ms=1.5, detail=None)
    fake = ReadyResponse(
        status="ok",
        checks=ReadyChecks(postgres=ok, redis=ok, redpanda=ok),
    )
    with patch("app.api.routes.health.run_readiness_checks", new=AsyncMock(return_value=fake)):
        r = await client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["postgres"]["status"] == "ok"
    assert "latency_ms" in body["checks"]["postgres"]


@pytest.mark.asyncio
async def test_ready_503_when_check_fails(client):
    ok = CheckResult(status="ok", latency_ms=1.0, detail=None)
    fail = CheckResult(status="fail", latency_ms=5.0, detail="ConnectionRefusedError")
    fake = ReadyResponse(
        status="not_ready",
        checks=ReadyChecks(postgres=fail, redis=ok, redpanda=ok),
    )
    with patch("app.api.routes.health.run_readiness_checks", new=AsyncMock(return_value=fake)):
        r = await client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"]["status"] == "fail"
    assert body["checks"]["postgres"]["detail"]


@pytest.mark.asyncio
async def test_ready_schema_shape(client):
    """Real TCP probes: accept 200 or 503 but require structured checks."""
    r = await client.get("/health/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    assert body["status"] in ("ok", "not_ready")
    for name in ("postgres", "redis", "redpanda"):
        check = body["checks"][name]
        assert check["status"] in ("ok", "fail", "skipped")
        assert "latency_ms" in check
        assert "detail" in check


def test_admin_index(sync_client):
    r = sync_client.get("/admin/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
