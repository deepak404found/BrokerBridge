"""VultrProvider unit tests — httpx mocked only (no live Vultr)."""

import pytest
import respx
from httpx import Response

from app.providers.infrastructure.vultr import VultrProvider, VULTR_API_BASE


@pytest.mark.asyncio
@respx.mock
async def test_vultr_probe_ok():
    respx.get(f"{VULTR_API_BASE}/account").mock(
        return_value=Response(200, json={"account": {"email": "lab@example.com"}})
    )
    provider = VultrProvider(api_key="fake-key", default_region="ewr")
    probe = await provider.probe()
    assert probe["ok"] is True
    assert probe["provider"] == "vultr"


@pytest.mark.asyncio
@respx.mock
async def test_vultr_probe_bad_key():
    respx.get(f"{VULTR_API_BASE}/account").mock(
        return_value=Response(401, json={"error": "Unauthorized"})
    )
    provider = VultrProvider(api_key="bad-key", default_region="ewr")
    probe = await provider.probe()
    assert probe["ok"] is False


@pytest.mark.asyncio
@respx.mock
async def test_vultr_create_ip_and_instance():
    respx.post(f"{VULTR_API_BASE}/reserved-ips").mock(
        return_value=Response(
            201,
            json={"reserved_ip": {"id": "rip-1", "subnet": "203.0.113.10", "region": "ewr"}},
        )
    )
    respx.post(f"{VULTR_API_BASE}/instances").mock(
        return_value=Response(
            202,
            json={"instance": {"id": "inst-1", "region": "ewr", "status": "pending"}},
        )
    )
    respx.post(f"{VULTR_API_BASE}/instances/inst-1/halt").mock(return_value=Response(204))
    respx.patch(f"{VULTR_API_BASE}/instances/inst-1").mock(return_value=Response(200, json={}))
    provider = VultrProvider(api_key="fake-key")
    ip = await provider.create_ip("ewr")
    assert ip["external_id"] == "rip-1"
    inst = await provider.create_instance("ewr")
    assert inst["external_id"] == "inst-1"
    await provider.set_auto_renew("inst-1", False)
    await provider.suspend_instance("inst-1")


@pytest.mark.asyncio
async def test_admin_vultr_fake_key_keeps_prior_mock(client):
    token_r = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    token = token_r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure mock active
    ok = await client.put(
        "/api/v1/admin/providers/infrastructure",
        headers=headers,
        json={
            "provider_type": "mock",
            "validate_first": True,
            "activate": True,
            "config": {"mock_backend": "database"},
        },
    )
    assert ok.status_code == 200
    prior_version = ok.json()["version"]

    with respx.mock:
        respx.get(f"{VULTR_API_BASE}/account").mock(
            return_value=Response(401, json={"error": "Unauthorized"})
        )
        bad = await client.put(
            "/api/v1/admin/providers/infrastructure",
            headers=headers,
            json={
                "provider_type": "vultr",
                "validate_first": True,
                "activate": True,
                "config": {"api_key": "definitely-fake", "default_region": "ewr"},
            },
        )
    assert bad.status_code == 422
    assert bad.json()["error_code"] == "PROVIDER_VALIDATION_FAILED"

    cur = await client.get("/api/v1/admin/providers/infrastructure", headers=headers)
    assert cur.status_code == 200
    body = cur.json()
    assert body["provider_type"] == "mock"
    assert body["version"] == prior_version
    assert body["config"].get("api_key", "***") in {"***", None} or "api_key" not in body["config"]
