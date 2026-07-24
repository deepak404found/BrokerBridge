"""Background workers: OutboxPublisher + EventConsumer + IpDrainWatcher."""

import asyncio
import logging

from app.config.settings import get_settings
from app.core.logging import setup_logging
from app.db.session import configure_engine, get_session_factory
from app.events.consumer import event_consumer_loop
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


async def subscription_expiry_loop(*, interval_seconds: float = 30.0) -> None:
    """Enforce BR-G07 subscription expiry teardown on an interval."""
    from app.subscriptions.service import SubscriptionService

    settings = get_settings()
    configure_engine(settings.database_url)
    factory = get_session_factory()
    manager = get_provider_manager()
    logger.info("subscription_expiry_scheduler_started")
    while True:
        try:
            async with factory() as session:
                svc = SubscriptionService(session, settings, manager)
                stats = await svc.enforce_expiry()
                if stats.get("expired"):
                    logger.info(
                        "subscription_expiry expired=%s torn_down=%s",
                        stats["expired"],
                        stats.get("instances_torn_down"),
                    )
        except Exception:  # noqa: BLE001
            logger.exception("subscription_expiry_tick_failed")
        await asyncio.sleep(interval_seconds)


async def async_main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    configure_engine(settings.database_url)
    logger.info("worker_started env=%s", settings.app_env)
    stop = asyncio.Event()
    try:
        await asyncio.gather(
            outbox_publisher_loop(),
            event_consumer_loop(group_suffix="", stop_event=stop),
            drain_watcher_loop(),
            subscription_expiry_loop(),
        )
    finally:
        stop.set()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("worker_stopped")


if __name__ == "__main__":
    main()
