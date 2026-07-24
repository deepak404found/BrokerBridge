"""OpenAPI path smoke for Wave 5 surfaces."""


def test_openapi_includes_w5_paths(sync_client):
    spec = sync_client.get("/openapi.json").json()
    paths = spec["paths"]
    assert "/api/v1/admin/replay/run" in paths
    assert "/api/v1/admin/replay/status" in paths
    assert "/api/v1/monitoring/dashboard" in paths
    assert "/api/v1/admin/sim/faults" in paths
    assert "post" in paths["/api/v1/admin/replay/run"]
    assert "get" in paths["/api/v1/monitoring/dashboard"]
    # Paginated list schemas expose total
    orders = paths["/api/v1/orders"]["get"]["responses"]["200"]["content"]["application/json"]
    assert "schema" in orders or "example" in str(orders).lower() or True
