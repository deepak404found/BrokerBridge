"""Docker mock infrastructure backend — skipped when Engine unavailable."""

import pytest

from app.providers.infrastructure.mock import MockInfrastructureProvider


def _docker_available() -> bool:
    try:
        import docker
    except ImportError:
        return False
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.docker


@pytest.mark.asyncio
async def test_docker_backend_instance_lifecycle():
    if not _docker_available():
        pytest.skip("Docker Engine / socket unavailable")
    provider = MockInfrastructureProvider(backend="docker")
    probe = await provider.probe()
    assert probe.get("ok") is True
    assert probe.get("backend") == "docker"
    inst = await provider.create_instance("ewr", label="w6-docker-test")
    await provider.suspend_instance(inst["external_id"])
    await provider.start_instance(inst["external_id"])
    ip = await provider.create_ip("ewr")
    assert ip["ip_address"].startswith(("198.51.100.", "203.0.113."))
    await provider.destroy_instance(inst["external_id"])
