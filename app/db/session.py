from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def configure_engine(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    global engine, SessionLocal
    url = database_url or get_settings().database_url
    engine = create_async_engine(url, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return SessionLocal


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if SessionLocal is None:
        configure_engine()
    assert SessionLocal is not None
    return SessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
