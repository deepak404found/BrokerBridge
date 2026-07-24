"""EventProvider consumer dispatch — feed bus buffer + thin monitoring hooks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.events.bus_buffer import get_bus_buffer
from app.events.envelope import DEFAULT_TOPIC_MAP, resolve_physical_topic
from app.providers.manager import ProviderManager

logger = logging.getLogger("brokerbridge.events.consumer")


def default_topics(*, topic_prefix: str | None = None, topic_map: dict[str, str] | None = None) -> list[str]:
    logicals = list(DEFAULT_TOPIC_MAP.keys())
    # Deduplicate when topic_map collapses many logicals onto one physical topic
    physical = [
        resolve_physical_topic(logical, topic_prefix=topic_prefix, topic_map=topic_map)
        for logical in logicals
    ]
    return list(dict.fromkeys(physical))


async def on_consumed_event(topic: str, event: dict[str, Any]) -> None:
    """Thin handler: buffer for Admin + counters. No duplicate order submit."""
    get_bus_buffer().append(topic=topic, event=event, source="consumed")
    logger.debug(
        "event_consumed topic=%s type=%s id=%s",
        topic,
        event.get("event_type"),
        event.get("event_id"),
    )


async def event_consumer_loop(
    *,
    group_suffix: str = "",
    poll_version_seconds: float = 2.0,
    stop_event: asyncio.Event | None = None,
    ready_event: asyncio.Event | None = None,
) -> None:
    """
    Subscribe via EventProvider; reconnect when kind=event version changes.

    group_suffix: e.g. '-api' so API fan-in does not compete with the worker group.
    """
    from app.db.session import get_session_factory
    from app.providers.manager import get_provider_manager

    providers = get_provider_manager()
    factory = get_session_factory()
    stop = stop_event or asyncio.Event()
    last_version: Any = object()
    consume_task: asyncio.Task[None] | None = None
    current_provider: Any = None

    logger.info("event_consumer_started suffix=%s", group_suffix or "(worker)")

    async def _cancel_consume() -> None:
        nonlocal consume_task, current_provider
        # Signal run_consumer to exit; full aclose happens via manager.invalidate → _stale
        if current_provider is not None:
            stop = getattr(current_provider, "_stop", None)
            if stop is not None:
                stop.set()
        if consume_task is not None:
            consume_task.cancel()
            try:
                await consume_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            consume_task = None
        current_provider = None

    try:
        while not stop.is_set():
            try:
                async with factory() as session:
                    version = await providers.active_event_version(session)
                    if version != last_version:
                        await _cancel_consume()
                        providers.invalidate("event")
                        provider = await providers.get_event_provider(session)
                        topic_prefix = getattr(provider, "topic_prefix", None)
                        topic_map = getattr(provider, "topic_map", None)
                        topics = default_topics(topic_prefix=topic_prefix, topic_map=topic_map)
                        base_group = getattr(provider, "consumer_group", None) or "brokerbridge-lab"
                        group = f"{base_group}{group_suffix}" if group_suffix else str(base_group)
                        await provider.subscribe(topics, on_consumed_event, consumer_group=group)
                        current_provider = provider
                        consume_task = asyncio.create_task(
                            provider.run_consumer(),
                            name=f"event-consumer{group_suffix or '-worker'}",
                        )
                        last_version = version
                        logger.info(
                            "event_consumer_subscribed version=%s group=%s topics=%s type=%s",
                            version,
                            group,
                            topics,
                            getattr(provider, "provider_type", "?"),
                        )
                        if ready_event is not None and not ready_event.is_set():
                            ready_event.set()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("event_consumer_tick_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=poll_version_seconds)
            except TimeoutError:
                pass
    finally:
        await _cancel_consume()
        logger.info("event_consumer_stopped")
