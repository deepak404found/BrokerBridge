"""Background workers: OutboxPublisher + IpDrainWatcher heartbeat."""

import asyncio
import logging

from app.config.settings import get_settings
from app.core.logging import setup_logging
from app.db.session import configure_engine, get_session_factory
from app.events.outbox import drain_outbox
from app.providers.manager import get_provider_manager
import app.models  # noqa: F401

logger = logging.getLogger("brokerbridge.worker")


async def outbox_publisher_loop(*, interval_seconds: float = 2.0) -> None:
    settings = get_settings()
    configure_engine(settings.database_url)
    factory = get_session_factory()
    manager = get_provider_manager()
    last_version: int | None = None
    logger.info("outbox_publisher_started")
    while True:
        try:
            async with factory() as session:
                version = await manager.active_event_version(session)
                if version != last_version:
                    manager.invalidate("event")
                    # Rebuild / reconnect producer
                    await manager.get_event_provider(session)
                    last_version = version
                    logger.info("event_provider_reconnected version=%s", version)
                stats = await drain_outbox(session, manager, limit=50)
                if stats["sent"] or stats["error"]:
                    logger.info("outbox_drain sent=%s error=%s", stats["sent"], stats["error"])
        except Exception:  # noqa: BLE001
            logger.exception("outbox_publisher_tick_failed")
        await asyncio.sleep(interval_seconds)


async def drain_watcher_loop(*, interval_seconds: float = 15.0) -> None:
    """Lightweight watcher for draining assignments (observability heartbeat)."""
    from sqlalchemy import func, select

    from app.models.infrastructure import IpAssignment

    settings = get_settings()
    configure_engine(settings.database_url)
    factory = get_session_factory()
    logger.info("ip_drain_watcher_started")
    while True:
        try:
            async with factory() as session:
                result = await session.execute(
                    select(func.count())
                    .select_from(IpAssignment)
                    .where(IpAssignment.status == "draining")
                )
                count = int(result.scalar_one() or 0)
                if count:
                    logger.info("ip_drain_watcher draining_assignments=%s", count)
        except Exception:  # noqa: BLE001
            logger.exception("ip_drain_watcher_failed")
        await asyncio.sleep(interval_seconds)


async def async_main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("worker_started env=%s", settings.app_env)
    await asyncio.gather(
        outbox_publisher_loop(),
        drain_watcher_loop(),
    )


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("worker_stopped")


if __name__ == "__main__":
    main()
