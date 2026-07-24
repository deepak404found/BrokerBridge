import itertools
from typing import Any
from uuid import uuid4

from app.sim.flags import infra_fault_enabled


class MockInfrastructureError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 503,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class MockInfrastructureProvider:
    """Mock cloud infra using documentation-range IPs (198.51.100.0/24, 203.0.113.0/24)."""

    def __init__(self) -> None:
        self._ip_counter = itertools.count(1)
        self._ips: dict[str, dict[str, Any]] = {}
        self._instances: dict[str, dict[str, Any]] = {}
        self._probe_fail: bool = False

    def set_probe_fail(self, enabled: bool) -> None:
        self._probe_fail = bool(enabled)

    def _fault_active(self) -> bool:
        return bool(self._probe_fail) or infra_fault_enabled()

    async def probe(self) -> dict[str, Any]:
        if self._fault_active():
            return {"ok": False, "provider": "mock", "error": "INFRA_UNAVAILABLE"}
        return {"ok": True, "provider": "mock"}

    def _next_ip(self, region: str) -> str:
        """Pick a documentation-range address unlikely to collide after process restart.

        The in-memory counter alone restarts at 1 when the API process restarts, but
        Postgres still holds previously allocated mock IPs — salt with uuid entropy.
        """
        n = next(self._ip_counter)
        salt = int(uuid4().hex[:8], 16)
        host = ((n + salt) % 254) + 1
        if (n + salt) % 2 == 0:
            return f"203.0.113.{host}"
        return f"198.51.100.{host}"

    async def create_ip(self, region: str, **kwargs: Any) -> dict[str, Any]:
        if self._fault_active():
            raise MockInfrastructureError(
                "INFRA_UNAVAILABLE",
                "Mock infrastructure injected fault (probe/create_ip)",
                status=503,
            )
        external_id = f"mock-ip-{uuid4().hex[:12]}"
        # Avoid reusing addresses already tracked in this process.
        used = {r.get("ip_address") for r in self._ips.values()}
        ip_address = self._next_ip(region)
        for _ in range(32):
            if ip_address not in used:
                break
            ip_address = self._next_ip(region)
        resource = {
            "id": external_id,
            "external_id": external_id,
            "ip_address": ip_address,
            "region": region,
            "status": "allocated",
            "provider": "mock",
        }
        self._ips[external_id] = resource
        return dict(resource)

    async def delete_ip(self, external_id: str) -> None:
        if external_id in self._ips:
            self._ips[external_id]["status"] = "released"

    async def attach_ip(self, external_id: str, instance_external_id: str) -> None:
        ip = self._ips.get(external_id)
        if ip is None:
            # Allow attach even if not tracked in-memory (DB is source of truth)
            self._ips[external_id] = {
                "external_id": external_id,
                "status": "attached",
                "instance_external_id": instance_external_id,
            }
        else:
            ip["status"] = "attached"
            ip["instance_external_id"] = instance_external_id

    async def detach_ip(self, external_id: str) -> None:
        ip = self._ips.get(external_id)
        if ip is not None:
            ip["status"] = "detached"
            ip.pop("instance_external_id", None)

    async def create_instance(self, region: str, **kwargs: Any) -> dict[str, Any]:
        external_id = f"mock-inst-{uuid4().hex[:12]}"
        resource = {
            "id": external_id,
            "external_id": external_id,
            "region": region,
            "status": "running",
            "provider": "mock",
            "label": kwargs.get("label") or f"Lab Instance {region}",
        }
        self._instances[external_id] = resource
        return dict(resource)

    async def destroy_instance(self, external_id: str) -> None:
        if external_id in self._instances:
            self._instances[external_id]["status"] = "destroyed"
