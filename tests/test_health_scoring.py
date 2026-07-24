import pytest

from app.health.service import compute_health_score, status_from_score


def test_health_score_formula_defaults():
    weights = {"w_lat": 0.25, "w_succ": 0.30, "w_conn": 0.15, "w_to": 0.20, "w_ip": 0.10}
    score = compute_health_score(
        latency_ms=0,
        success_rate=1.0,
        timeout_rate=0.0,
        connectivity=True,
        ip_health=100,
        weights=weights,
        latency_budget_ms=500,
    )
    assert score == pytest.approx(100.0)


def test_health_score_unhealthy_connectivity():
    weights = {"w_lat": 0.25, "w_succ": 0.30, "w_conn": 0.15, "w_to": 0.20, "w_ip": 0.10}
    score = compute_health_score(
        latency_ms=500,
        success_rate=0.0,
        timeout_rate=1.0,
        connectivity=False,
        ip_health=0,
        weights=weights,
        latency_budget_ms=500,
    )
    assert score == pytest.approx(0.0)
    assert status_from_score(score, {"healthy_min": 80, "degraded_min": 50}) == "unhealthy"


def test_status_thresholds():
    assert status_from_score(80, {"healthy_min": 80, "degraded_min": 50}) == "healthy"
    assert status_from_score(79.9, {"healthy_min": 80, "degraded_min": 50}) == "degraded"
    assert status_from_score(49.9, {"healthy_min": 80, "degraded_min": 50}) == "unhealthy"


@pytest.mark.asyncio
async def test_health_probe_api(client):
    token = (
        await client.post(
            "/api/v1/auth/token",
            data={"username": "admin@brokerbridge.local", "password": "admin123!"},
        )
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    probe = await client.post("/api/v1/monitoring/brokers/health/probe", headers=headers)
    assert probe.status_code == 200
    rows = probe.json()
    assert len(rows) >= 2
    assert all("score" in r and "status" in r and "breakdown" in r for r in rows)

    listed = await client.get("/api/v1/monitoring/brokers/health", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) >= 2
