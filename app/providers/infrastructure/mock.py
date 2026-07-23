from typing import Any
from uuid import uuid4


class MockInfrastructureProvider:
    async def probe(self) -> dict[str, Any]:
        return {"ok": True, "provider": "mock"}

    async def create_ip(self, region: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "id": str(uuid4()),
            "ip_address": f"198.51.100.{(hash(region) % 200) + 1}",
            "region": region,
            "status": "allocated",
        }
