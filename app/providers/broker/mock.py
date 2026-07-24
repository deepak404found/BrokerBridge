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
        self._orders: dict[str, dict[str, Any]] = {}
        self._fail_remaining: int = 0
        self._fail_status: int = 503
        self._fail_code: str = "BROKER_UNAVAILABLE"

    def fail_next_n(self, n: int, *, status: int = 503, code: str = "BROKER_UNAVAILABLE") -> None:
        """Test hook: next N place_order calls raise a retryable failure."""
        self._fail_remaining = max(0, int(n))
        self._fail_status = status
        self._fail_code = code

    async def probe(self) -> dict[str, Any]:
        return {
            "ok": True,
            "provider": "mock",
            "success_rate": 1.0,
            "timeout_rate": 0.0,
        }

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise MockBrokerError(
                self._fail_code,
                f"Mock broker injected failure ({self._fail_status})",
                status=self._fail_status,
                retryable=True,
            )
        broker_order_id = f"mock-{uuid.uuid4().hex[:8]}"
        result = {
            "status": "accepted",
            "broker_order_id": broker_order_id,
            "echo": payload,
        }
        self._orders[broker_order_id] = result
        return result

    async def cancel_order(
        self, broker_order_id: str, *, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        existing = self._orders.get(broker_order_id)
        if existing is None and not broker_order_id.startswith("mock-"):
            raise MockBrokerError(
                "ORDER_NOT_FOUND",
                f"Unknown broker order {broker_order_id}",
                status=404,
                retryable=False,
            )
        cancelled = {
            "status": "cancelled",
            "broker_order_id": broker_order_id,
            "echo": payload or {},
        }
        self._orders[broker_order_id] = cancelled
        return cancelled

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


class MockBrokerError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 503,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable
