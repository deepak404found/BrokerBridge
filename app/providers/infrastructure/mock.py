"""Mock infrastructure facade — delegates to database or docker backends."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.providers.infrastructure.errors import MockInfrastructureError

__all__ = ["MockInfrastructureError", "MockInfrastructureProvider"]


class MockInfrastructureProvider:
    """Facade over MOCK_INFRA_BACKEND=database|docker.

    Domain code depends only on InfrastructureProvider methods — never Docker/DB internals.
    """

    def __init__(
        self,
        *,
        backend: str = "database",
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        docker_host: str | None = None,
    ) -> None:
        name = (backend or "database").strip().lower()
        if name not in {"database", "docker"}:
            name = "database"
        self.backend_name = name
        if name == "docker":
            from app.providers.infrastructure.mock_docker import DockerMockBackend

            self._backend = DockerMockBackend(docker_host=docker_host)
        else:
            from app.providers.infrastructure.mock_database import DatabaseMockBackend

            self._backend = DatabaseMockBackend(session_factory=session_factory)

    def set_probe_fail(self, enabled: bool) -> None:
        self._backend.set_probe_fail(enabled)

    async def probe(self) -> dict[str, Any]:
        return await self._backend.probe()

    async def create_ip(self, region: str, **kwargs: Any) -> dict[str, Any]:
        return await self._backend.create_ip(region, **kwargs)

    async def delete_ip(self, external_id: str) -> None:
        await self._backend.delete_ip(external_id)

    async def attach_ip(self, external_id: str, instance_external_id: str) -> None:
        await self._backend.attach_ip(external_id, instance_external_id)

    async def detach_ip(self, external_id: str) -> None:
        await self._backend.detach_ip(external_id)

    async def create_instance(self, region: str, **kwargs: Any) -> dict[str, Any]:
        return await self._backend.create_instance(region, **kwargs)

    async def destroy_instance(self, external_id: str) -> None:
        await self._backend.destroy_instance(external_id)

    async def suspend_instance(self, external_id: str) -> None:
        await self._backend.suspend_instance(external_id)

    async def start_instance(self, external_id: str) -> None:
        await self._backend.start_instance(external_id)

    async def set_auto_renew(self, resource_id: str, enabled: bool) -> None:
        await self._backend.set_auto_renew(resource_id, enabled)

    async def list_ips(self, region: str | None = None) -> list[dict[str, Any]]:
        return await self._backend.list_ips(region)

    async def get_ip(self, external_id: str) -> dict[str, Any] | None:
        return await self._backend.get_ip(external_id)
