"""InfrastructureProvider protocol + manager resolution (Wave 6)."""

import ast
from pathlib import Path

import pytest

from app.db.session import get_session_factory
from app.providers.infrastructure.mock import MockInfrastructureProvider
from app.providers.manager import get_provider_manager


def test_domain_packages_do_not_import_docker_or_vultr():
    roots = [Path("app/ip_manager"), Path("app/orders"), Path("app/routing"), Path("app/subscriptions")]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("docker"), f"{path} imports {alias.name}"
                        assert "vultr" not in alias.name.lower(), f"{path} imports {alias.name}"
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith("docker"), path
                    assert "providers.infrastructure.vultr" not in node.module, path
                    assert not node.module.startswith("app.providers.infrastructure.vultr"), path


@pytest.mark.asyncio
async def test_manager_resolves_database_backend(configured_app, monkeypatch):
    monkeypatch.setenv("MOCK_INFRA_BACKEND", "database")
    from app.config.settings import get_settings
    from app.providers import manager as pm

    get_settings.cache_clear()
    pm._manager = None
    factory = get_session_factory()
    manager = get_provider_manager()
    async with factory() as session:
        infra = await manager.get_infrastructure_provider(session)
        desc = await manager.describe_infrastructure(session)
    assert isinstance(infra, MockInfrastructureProvider)
    assert infra.backend_name == "database"
    assert desc["backend"] == "database"
    probe = await infra.probe()
    assert probe.get("ok") is True
    assert probe.get("backend") == "database"


@pytest.mark.asyncio
async def test_protocol_methods_on_mock(configured_app):
    factory = get_session_factory()
    manager = get_provider_manager()
    async with factory() as session:
        infra = await manager.get_infrastructure_provider(session)
    inst = await infra.create_instance("ewr", label="proto")
    assert inst["external_id"]
    await infra.set_auto_renew(inst["external_id"], False)
    await infra.suspend_instance(inst["external_id"])
    await infra.start_instance(inst["external_id"])
    ip = await infra.create_ip("ewr")
    assert ip["ip_address"].startswith(("198.51.100.", "203.0.113."))
    listed = await infra.list_ips(region="ewr")
    assert any(r["external_id"] == ip["external_id"] for r in listed)
    got = await infra.get_ip(ip["external_id"])
    assert got is not None
    await infra.destroy_instance(inst["external_id"])
