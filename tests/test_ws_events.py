"""WebSocket outbox feed for Admin Event Bus auto-refresh."""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect
from fastapi.testclient import TestClient


def _token(sync_client: TestClient) -> str:
    r = sync_client.post(
        "/api/v1/auth/token",
        data={"username": "admin@brokerbridge.local", "password": "admin123!"},
    )
    assert r.status_code == 200
    return r.json()["access_token"]


def test_ws_events_rejects_missing_token(sync_client: TestClient):
    with pytest.raises(WebSocketDisconnect):
        with sync_client.websocket_connect("/api/v1/ws/events") as ws:
            ws.receive_json()


def test_ws_events_sends_snapshot_and_updates(sync_client: TestClient):
    token = _token(sync_client)
    headers = {"Authorization": f"Bearer {token}"}
    with sync_client.websocket_connect(f"/api/v1/ws/events?token={token}&limit=20") as ws:
        first = ws.receive_json()
        assert first["type"] == "snapshot"
        assert isinstance(first["events"], list)
        assert "fingerprint" in first

        # Mutate config → outbox row; WS should push an update without client reload
        r = sync_client.put(
            "/api/v1/admin/config/ip.rotation.drain_timeout_seconds",
            headers=headers,
            json={"value": {"seconds": 31}},
        )
        assert r.status_code == 200

        second = ws.receive_json()
        assert second["type"] in {"snapshot", "update"}
        assert isinstance(second["events"], list)
        types = [e.get("event_type") for e in second["events"]]
        assert "config.updated" in types
