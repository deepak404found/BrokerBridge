import pytest
from tests.helpers import as_items


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
async def test_w2_openapi_examples_realistic(client):
    res = await client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    paths = schema["paths"]
    components = schema.get("components", {}).get("schemas", {})

    required = [
        "/api/v1/brokers",
        "/api/v1/brokers/{broker_id}",
        "/api/v1/brokers/{broker_id}/capabilities/refresh",
        "/api/v1/brokers/{broker_id}/sessions/ensure",
        "/api/v1/infrastructure/ips",
        "/api/v1/infrastructure/ips/{ip_id}/assign",
        "/api/v1/infrastructure/ips/{ip_id}/attach",
        "/api/v1/infrastructure/assignments",
        "/api/v1/infrastructure/brokers/{broker_id}/whitelist/sync",
        "/api/v1/monitoring/sessions",
    ]
    for p in required:
        assert p in paths, f"missing path {p}"

    post_broker = paths["/api/v1/brokers"]["post"]
    content = post_broker["requestBody"]["content"]["application/json"]
    example = _extract_example(content)
    if isinstance(example, str) and example.startswith("#/"):
        name = example.rsplit("/", 1)[-1]
        example = components[name].get("example") or (components[name].get("examples") or [None])[0]
    assert example is not None
    blob = str(example)
    for frag in PLACEHOLDER_FRAGMENTS:
        assert frag not in blob
    assert "mock" in blob.lower() or "display_name" in blob

    allocate = paths["/api/v1/infrastructure/ips"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]
    alloc_ex = _extract_example(allocate)
    assert "198.51.100" in str(alloc_ex) or "ip_address" in str(alloc_ex)
