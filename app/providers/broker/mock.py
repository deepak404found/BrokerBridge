import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any


_DEFAULT_CAPS = {
    "asset_classes": ["equities", "options"],
    "order_types": ["MARKET", "LIMIT"],
    "time_in_force": ["DAY", "GTC"],
    "supports_whitelist": True,
    "regions": ["ewr", "ord", "lax"],
}


class MockBrokerProvider:
    """In-process mock broker — no real HTTP."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    async def probe(self) -> dict[str, Any]:
        return {"ok": True, "provider": "mock"}

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "accepted", "broker_order_id": f"mock-{uuid.uuid4().hex[:8]}", "echo": payload}

    async def authenticate(self, credentials: dict[str, Any]) -> dict[str, Any]:
        access = f"mock-access-{uuid.uuid4().hex}"
        refresh = f"mock-refresh-{uuid.uuid4().hex}"
        expires = datetime.now(UTC) + timedelta(hours=1)
        self._sessions[access] = {"refresh": refresh, "expires_at": expires.isoformat()}
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_at": expires.isoformat(),
            "status": "valid",
            "credentials_echo_keys": sorted(credentials.keys()),
        }

    async def refresh_session(self, refresh_token: str | None) -> dict[str, Any]:
        access = f"mock-access-{uuid.uuid4().hex}"
        refresh = refresh_token or f"mock-refresh-{uuid.uuid4().hex}"
        expires = datetime.now(UTC) + timedelta(hours=1)
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_at": expires.isoformat(),
            "status": "valid",
        }

    async def list_capabilities(self) -> dict[str, Any]:
        return dict(_DEFAULT_CAPS)

    async def fetch_whitelist_raw(self, *, format_hint: str | None = None) -> dict[str, Any]:
        fmt = (format_hint or "json").lower()
        if fmt == "xml":
            payload = (
                '<?xml version="1.0"?>'
                "<whitelist>"
                "<ip>198.51.100.10</ip>"
                "<ip>198.51.100.11</ip>"
                "</whitelist>"
            )
            return {"format": "xml", "payload": payload}
        payload = json.dumps(
            {
                "ips": ["198.51.100.10", "198.51.100.11", "203.0.113.5"],
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        return {"format": "json", "payload": payload}
