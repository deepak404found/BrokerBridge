"""Database mock infrastructure backend."""

import pytest

from app.providers.infrastructure.mock import MockInfrastructureError, MockInfrastructureProvider
from app.db.session import get_session_factory


@pytest.mark.asyncio
async def test_database_backend_ip_lifecycle(configured_app):
    factory = get_session_factory()
    provider = MockInfrastructureProvider(backend="database", session_factory=factory)
    assert provider.backend_name == "database"
    ip = await provider.create_ip("ord")
    assert ip["backend"] == "database"
    await provider.attach_ip(ip["external_id"], "mock-inst-x")
    await provider.detach_ip(ip["external_id"])
    await provider.delete_ip(ip["external_id"])
    got = await provider.get_ip(ip["external_id"])
    assert got is None or got.get("status") == "released"


@pytest.mark.asyncio
async def test_database_backend_suspend_and_auto_renew(configured_app):
    factory = get_session_factory()
    provider = MockInfrastructureProvider(backend="database", session_factory=factory)
    inst = await provider.create_instance("ewr")
    await provider.set_auto_renew(inst["external_id"], False)
    await provider.suspend_instance(inst["external_id"])
    await provider.destroy_instance(inst["external_id"])


@pytest.mark.asyncio
async def test_database_fault_injection(configured_app):
    provider = MockInfrastructureProvider(backend="database")
    provider.set_probe_fail(True)
    probe = await provider.probe()
    assert probe["ok"] is False
    with pytest.raises(MockInfrastructureError):
        await provider.create_ip("ewr")
