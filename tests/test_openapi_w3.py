import pytest


PLACEHOLDER_FRAGMENTS = ('"string"', "additionalProp1", "'string'")


def _extract_example(content: dict):
    if content.get("example") is not None:
        return content["example"]
    examples = content.get("examples") or {}
    if examples:
        first = next(iter(examples.values()))
        if isinstance(first, dict) and "value" in first:
            return first["value"]
        return first
    schema = content.get("schema") or {}
    if "example" in schema:
        return schema["example"]
    if schema.get("examples"):
        return schema["examples"][0]
    return schema.get("$ref")


@pytest.mark.asyncio
async def test_w3_openapi_paths_and_examples(client):
    res = await client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    paths = schema["paths"]

    required = [
        "/api/v1/orders/buy",
        "/api/v1/orders/sell",
        "/api/v1/orders/{order_id}",
        "/api/v1/orders/{order_id}/cancel",
        "/api/v1/orders",
        "/api/v1/monitoring/brokers/health",
        "/api/v1/monitoring/brokers/health/probe",
        "/api/v1/monitoring/rate-limits",
        "/api/v1/monitoring/failovers",
        "/api/v1/monitoring/orders/engine",
        "/api/v1/monitoring/routing/preview",
        "/api/v1/admin/config",
        "/api/v1/admin/config/{key}",
    ]
    for p in required:
        assert p in paths, f"missing path {p}"

    buy = paths["/api/v1/orders/buy"]["post"]
    content = buy["requestBody"]["content"]["application/json"]
    example = _extract_example(content)
    assert example is not None
    blob = str(example)
    for frag in PLACEHOLDER_FRAGMENTS:
        assert frag not in blob
    assert "AAPL" in blob or "client_order_id" in blob

    health = paths["/api/v1/monitoring/brokers/health"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]
    hexample = _extract_example(health)
    assert "score" in str(hexample) or "healthy" in str(hexample)
