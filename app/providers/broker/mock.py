from typing import Any


class MockBrokerProvider:
    async def probe(self) -> dict[str, Any]:
        return {"ok": True, "provider": "mock"}

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": "accepted", "broker_order_id": "mock-1", "echo": payload}
