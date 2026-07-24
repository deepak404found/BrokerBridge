import pytest


@pytest.mark.asyncio
async def test_openapi_includes_w4_paths(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/infrastructure/brokers/{broker_id}/rotate-ip" in paths
    assert "/api/v1/monitoring/events" in paths
    assert "/api/v1/monitoring/events/drain" in paths
    assert "/api/v1/admin/providers/{kind}" in paths
    # kind=event is path param — ensure schema mentions event kinds via components still present
    assert "post" in paths["/api/v1/infrastructure/brokers/{broker_id}/rotate-ip"]
    assert "get" in paths["/api/v1/monitoring/events"]
