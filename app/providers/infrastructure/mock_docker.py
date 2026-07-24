"""Docker Engine mock infrastructure backend (Local Lab opt-in)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from app.providers.infrastructure.docnet import DocNetIpAllocator
from app.providers.infrastructure.docker_util import DOCKER_SOCKET_HINT
from app.providers.infrastructure.errors import MockInfrastructureError
from app.sim.flags import infra_fault_enabled

logger = logging.getLogger("brokerbridge.providers.mock_docker")

LABEL_KEY = "brokerbridge.mock"
LABEL_VALUE = "1"


class DockerMockBackend:
    """Map instances to Docker containers; IPs remain DOC-NET simulated."""

    def __init__(self, docker_host: str | None = None) -> None:
        self._docker_host = docker_host
        self._client = None
        self._allocator = DocNetIpAllocator()
        self._ips: dict[str, dict[str, Any]] = {}
        self._instances: dict[str, dict[str, Any]] = {}
        self._probe_fail: bool = False
        self.backend_name = "docker"

    def set_probe_fail(self, enabled: bool) -> None:
        self._probe_fail = bool(enabled)

    def _fault_active(self) -> bool:
        return bool(self._probe_fail) or infra_fault_enabled()

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import docker
        except ImportError as exc:
            raise MockInfrastructureError(
                "DOCKER_SDK_MISSING",
                "docker package required for MOCK_INFRA_BACKEND=docker "
                "(poetry install --extras infra-docker)",
                status=503,
            ) from exc
        try:
            if self._docker_host:
                self._client = docker.DockerClient(base_url=self._docker_host)
            else:
                self._client = docker.from_env()
        except Exception as exc:  # noqa: BLE001
            raise MockInfrastructureError(
                "DOCKER_UNAVAILABLE",
                f"{DOCKER_SOCKET_HINT} ({exc})",
                status=503,
            ) from exc
        return self._client

    async def probe(self) -> dict[str, Any]:
        if self._fault_active():
            return {
                "ok": False,
                "provider": "mock",
                "backend": self.backend_name,
                "error": "INFRA_UNAVAILABLE",
            }
        try:
            client = self._get_client()
            client.ping()
            return {"ok": True, "provider": "mock", "backend": self.backend_name}
        except MockInfrastructureError as exc:
            return {
                "ok": False,
                "provider": "mock",
                "backend": self.backend_name,
                "error": exc.code,
                "message": exc.message,
                "hint": DOCKER_SOCKET_HINT,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "provider": "mock",
                "backend": self.backend_name,
                "error": "DOCKER_UNAVAILABLE",
                "message": f"{DOCKER_SOCKET_HINT} ({exc})",
                "hint": DOCKER_SOCKET_HINT,
            }

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
            "backend": "docker",
            "note": "DOC-NET simulated IP (not container network IP)",
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
        client = self._get_client()
        external_id = f"mock-inst-{uuid4().hex[:12]}"
        label = kwargs.get("label") or f"Lab Instance {region}"
        name = f"bb-mock-{external_id[-12:]}"
        try:
            # Prefer a tiny image already common in Local Lab hosts.
            container = client.containers.run(
                "alpine:3.20",
                command=["sleep", "infinity"],
                detach=True,
                name=name,
                labels={LABEL_KEY: LABEL_VALUE, "brokerbridge.external_id": external_id},
                remove=False,
            )
            container_id = container.id
        except Exception as exc:  # noqa: BLE001
            logger.warning("docker_create_failed err=%s", exc)
            raise MockInfrastructureError(
                "DOCKER_CREATE_FAILED",
                f"Failed to create mock container: {exc}",
                status=503,
            ) from exc
        resource = {
            "id": external_id,
            "external_id": external_id,
            "region": region,
            "status": "running",
            "provider": "mock",
            "backend": "docker",
            "label": label,
            "container_id": container_id,
            "auto_renew": True,
        }
        self._instances[external_id] = resource
        return dict(resource)

    def _container_for(self, external_id: str):
        client = self._get_client()
        meta = self._instances.get(external_id) or {}
        cid = meta.get("container_id")
        if cid:
            try:
                return client.containers.get(cid)
            except Exception:  # noqa: BLE001
                pass
        # Label lookup (survives process restart within same Docker daemon)
        matches = client.containers.list(
            all=True,
            filters={"label": [f"{LABEL_KEY}={LABEL_VALUE}", f"brokerbridge.external_id={external_id}"]},
        )
        if matches:
            return matches[0]
        return None

    async def destroy_instance(self, external_id: str) -> None:
        container = self._container_for(external_id)
        if container is not None:
            try:
                container.remove(force=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("docker_destroy_failed id=%s err=%s", external_id, exc)
        if external_id in self._instances:
            self._instances[external_id]["status"] = "destroyed"

    async def suspend_instance(self, external_id: str) -> None:
        container = self._container_for(external_id)
        if container is not None:
            try:
                container.stop(timeout=5)
            except Exception as exc:  # noqa: BLE001
                logger.warning("docker_suspend_failed id=%s err=%s", external_id, exc)
                raise MockInfrastructureError(
                    "DOCKER_SUSPEND_FAILED",
                    f"Failed to stop mock container: {exc}",
                    status=503,
                ) from exc
        if external_id in self._instances:
            self._instances[external_id]["status"] = "suspended"

    async def start_instance(self, external_id: str) -> None:
        container = self._container_for(external_id)
        if container is not None:
            try:
                container.start()
            except Exception as exc:  # noqa: BLE001
                raise MockInfrastructureError(
                    "DOCKER_START_FAILED",
                    f"Failed to start mock container: {exc}",
                    status=503,
                ) from exc
        if external_id in self._instances:
            self._instances[external_id]["status"] = "running"

    async def set_auto_renew(self, resource_id: str, enabled: bool) -> None:
        for store in (self._instances, self._ips):
            if resource_id in store:
                store[resource_id]["auto_renew"] = bool(enabled)

    async def list_ips(self, region: str | None = None) -> list[dict[str, Any]]:
        rows = list(self._ips.values())
        if region:
            rows = [r for r in rows if r.get("region") == region]
        return [dict(r) for r in rows]

    async def get_ip(self, external_id: str) -> dict[str, Any] | None:
        row = self._ips.get(external_id)
        return dict(row) if row else None
