import app.providers.manager as provider_manager
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.config.settings import get_settings
from app.db import session as db_session
from app.db.base import Base
from app.db.seed import seed_defaults
from app.main import create_app
import app.models  # noqa: F401


@pytest.fixture
def sqlite_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"


def _force_memory_providers(monkeypatch, sqlite_url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", sqlite_url)
    monkeypatch.setenv("SEED_ADMIN_EMAIL", "admin@brokerbridge.local")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "admin123!")
    # Keep pytest on in-process providers even if Local Lab .env uses Redis hosts.
    monkeypatch.setenv("LOCK_PROVIDER", "memory")
    monkeypatch.setenv("SESSION_PROVIDER", "memory")
    monkeypatch.setenv("RATE_LIMIT_PROVIDER", "memory")
    monkeypatch.setenv("EVENT_PROVIDER", "memory")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
async def configured_app(sqlite_url, monkeypatch):
    _force_memory_providers(monkeypatch, sqlite_url)
    get_settings.cache_clear()
    db_session.engine = None
    db_session.SessionLocal = None
    provider_manager._manager = None

    from app.events.bus_buffer import reset_bus_buffer_for_tests
    from app.sim.service import reset_sim_for_tests

    reset_bus_buffer_for_tests()
    reset_sim_for_tests()

    settings = get_settings()
    factory = db_session.configure_engine(settings.database_url)
    assert db_session.engine is not None
    async with db_session.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as session:
        await seed_defaults(session, settings)

    app = create_app()
    yield app

    if db_session.engine is not None:
        await db_session.engine.dispose()
    get_settings.cache_clear()
    db_session.engine = None
    db_session.SessionLocal = None
    provider_manager._manager = None
    reset_bus_buffer_for_tests()
    reset_sim_for_tests()


@pytest.fixture
async def client(configured_app):
    transport = ASGITransport(app=configured_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sync_client(sqlite_url, monkeypatch):
    """Sync TestClient with its own sqlite DB (lifespan creates schema)."""
    _force_memory_providers(monkeypatch, sqlite_url)
    get_settings.cache_clear()
    db_session.engine = None
    db_session.SessionLocal = None
    provider_manager._manager = None
    from app.events.bus_buffer import reset_bus_buffer_for_tests
    from app.sim.service import reset_sim_for_tests

    reset_bus_buffer_for_tests()
    reset_sim_for_tests()
    app = create_app()
    with TestClient(app) as tc:
        yield tc
    get_settings.cache_clear()
    db_session.engine = None
    db_session.SessionLocal = None
    provider_manager._manager = None
    reset_bus_buffer_for_tests()
    reset_sim_for_tests()
