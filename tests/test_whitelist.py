import pytest

from app.whitelist.service import normalize_whitelist


def test_normalize_json_and_xml():
    j = normalize_whitelist(
        "json",
        '{"ips": ["198.51.100.10", "198.51.100.11", "198.51.100.10"]}',
    )
    assert j["ips"] == ["198.51.100.10", "198.51.100.11"]
    assert j["count"] == 2

    x = normalize_whitelist(
        "xml",
        '<?xml version="1.0"?><whitelist><ip>203.0.113.1</ip><ip>203.0.113.2</ip></whitelist>',
    )
    assert x["ips"] == ["203.0.113.1", "203.0.113.2"]


@pytest.mark.asyncio
async def test_whitelist_sync_persists_findings(client):
    login = await client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    brokers = (await client.get("/api/v1/brokers", headers=headers)).json()
    broker_id = brokers[0]["id"]

    # Allocate + assign so expected set is non-empty → missing findings vs mock whitelist
    ip = (
        await client.post("/api/v1/infrastructure/ips", headers=headers, json={"region": "ewr"})
    ).json()
    await client.post(
        f"/api/v1/infrastructure/ips/{ip['id']}/assign",
        headers=headers,
        json={"broker_account_id": broker_id},
    )

    sync = await client.post(
        f"/api/v1/infrastructure/brokers/{broker_id}/whitelist/sync",
        headers=headers,
    )
    assert sync.status_code == 200
    body = sync.json()
    assert body["raw_format"] in ("json", "xml")
    assert "ips" in body["normalized"]
    assert body["snapshot_id"]
    assert len(body["findings"]) >= 1
    types = {f["finding_type"] for f in body["findings"]}
    assert "missing" in types or "ok" in types or "unauthorized" in types
