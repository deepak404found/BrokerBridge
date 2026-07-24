"""Database mock infrastructure backend (CI / Render / default).

Uses in-process DOC-NET simulation (no Docker). Domain tables (`instances`,
`static_ips`) remain the durable source of truth; this backend never opens a
nested DB session during caller transactions (avoids SQLite lock issues).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.providers.infrastructure.docnet import DocNetIpAllocator
from app.providers.infrastructure.errors import MockInfrastructureError
from app.sim.flags import infra_fault_enabled


class DatabaseMockBackend:
    """Simulate cloud instances/IPs without Docker or Vultr."""

    def __init__(self, session_factory: Any = None) -> None:
        # session_factory retained for API compatibility; unused (see module docstring).
        self._session_factory = session_factory
        self._allocator = DocNetIpAllocator()
        self._ips: dict[str, dict[str, Any]] = {}
        self._instances: dict[str, dict[str, Any]] = {}
        self._probe_fail: bool = False
        self.backend_name = "database"

    def set_probe_fail(self, enabled: bool) -> None:
        self._probe_fail = bool(enabled)

    def _fault_active(self) -> bool:
        return bool(self._probe_fail) or infra_fault_enabled()

    async def probe(self) -> dict[str, Any]:
        if self._fault_active():
            return {
                "ok": False,
                "provider": "mock",
                "backend": self.backend_name,
                "error": "INFRA_UNAVAILABLE",
            }
        return {"ok": True, "provider": "mock", "backend": self.backend_name}

    async def create_ip(self, region: str, **kwargs: Any) -> dict[str, Any]:
        if self._fault_active():
            raise MockInfrastructureError(
                "INFRA_UNAVAILABLE",
                "Mock infrastructure injected fault (probe/create_ip)",
                status=503,
            )
        external_id = f"mock-ip-{uuid4().hex[:12]}"
        used = {r.get("ip_address") for r in self._ips.values() if r.get("ip_address")}
        ip_address = self._allocator.next_address(used=used)
        resource = {
            "id": external_id,
            "external_id": external_id,
            "ip_address": ip_address,
            "region": region,
            "status": "allocated",
            "provider": "mock",
            "backend": "database",
            "auto_renew": True,
        }
        self._ips[external_id] = resource
        return dict(resource)

    async def delete_ip(self, external_id: str) -> None:
        if external_id in self._ips:
            self._ips[external_id]["status"] = "released"

    async def attach_ip(self, external_id: str, instance_external_id: str) -> None:
        ip = self._ips.get(external_id)
        if ip is None:
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
        if self._fault_active():
            raise MockInfrastructureError(
                "INFRA_UNAVAILABLE",
                "Mock infrastructure injected fault (create_instance)",
                status=503,
            )
        external_id = f"mock-inst-{uuid4().hex[:12]}"
        label = kwargs.get("label") or f"Lab Instance {region}"
        resource = {
            "id": external_id,
            "external_id": external_id,
            "region": region,
            "status": "running",
            "provider": "mock",
            "backend": "database",
            "label": label,
            "auto_renew": True,
        }
        self._instances[external_id] = resource
        return dict(resource)

    async def destroy_instance(self, external_id: str) -> None:
        if external_id in self._instances:
            self._instances[external_id]["status"] = "destroyed"

    async def suspend_instance(self, external_id: str) -> None:
        if external_id in self._instances:
            self._instances[external_id]["status"] = "suspended"
        else:
            # Domain may hold external_id after process restart — allow soft track
            self._instances[external_id] = {
                "external_id": external_id,
                "status": "suspended",
                "provider": "mock",
                "backend": "database",
            }

    async def start_instance(self, external_id: str) -> None:
        if external_id in self._instances:
            self._instances[external_id]["status"] = "running"
        else:
            self._instances[external_id] = {
                "external_id": external_id,
                "status": "running",
                "provider": "mock",
                "backend": "database",
            }

    async def set_auto_renew(self, resource_id: str, enabled: bool) -> None:
        for store in (self._instances, self._ips):
            if resource_id in store:
                store[resource_id]["auto_renew"] = bool(enabled)
                return
        self._instances[resource_id] = {
            "external_id": resource_id,
            "auto_renew": bool(enabled),
            "status": "running",
            "provider": "mock",
            "backend": "database",
        }

    async def list_ips(self, region: str | None = None) -> list[dict[str, Any]]:
        rows = list(self._ips.values())
        if region:
            rows = [r for r in rows if r.get("region") == region]
        return [dict(r) for r in rows]

    async def get_ip(self, external_id: str) -> dict[str, Any] | None:
        row = self._ips.get(external_id)
        return dict(row) if row else None
