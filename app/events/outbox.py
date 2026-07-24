from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.envelope import build_envelope, resolve_physical_topic
from app.models.outbox import OutboxEvent
from app.providers.manager import ProviderManager

logger = logging.getLogger("brokerbridge.outbox")


def enqueue_outbox(
    session: AsyncSession,
    *,
    event_type: str,
    payload: dict[str, Any],
    topic: str = "ip",
    correlation_id: str | None = None,
) -> OutboxEvent:
    """Stage an outbox row on the current session (same TX as domain mutation)."""
    row = OutboxEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        topic=topic,
        payload=payload,
        status="pending",
        correlation_id=correlation_id,
    )
    session.add(row)
    return row


async def list_outbox(
    session: AsyncSession,
    *,
    limit: int = 50,
    status: str | None = None,
) -> list[OutboxEvent]:
    q = select(OutboxEvent).order_by(OutboxEvent.created_at.desc()).limit(min(limit, 200))
    if status:
        q = q.where(OutboxEvent.status == status)
    result = await session.execute(q)
    return list(result.scalars().all())


async def drain_outbox(
    session: AsyncSession,
    providers: ProviderManager,
    *,
    limit: int = 50,
    producer: str = "brokerbridge-worker",
) -> dict[str, int]:
    """Publish pending outbox rows via EventProvider; mark sent/error."""
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.status == "pending")
        .order_by(OutboxEvent.created_at.asc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    if not rows:
        return {"sent": 0, "error": 0, "pending": 0}

    event_provider = await providers.get_event_provider(session)
    topic_prefix = getattr(event_provider, "topic_prefix", None)
    topic_map = getattr(event_provider, "topic_map", None)

    sent = 0
    errors = 0
    for row in rows:
        envelope = build_envelope(
            row.event_type,
            row.payload,
            producer=producer,
            correlation_id=row.correlation_id,
            event_id=row.id,
        )
        physical = resolve_physical_topic(
            row.topic,
            topic_prefix=topic_prefix,
            topic_map=topic_map,
        )
        try:
            await event_provider.publish(physical, envelope)
            row.status = "sent"
            row.sent_at = datetime.now(UTC)
            sent += 1
        except Exception as exc:  # noqa: BLE001 — persist and continue drain
            logger.exception("outbox_publish_failed id=%s type=%s", row.id, row.event_type)
            row.status = "error"
            row.error = str(exc)[:2000]
            errors += 1
    await session.commit()
    return {"sent": sent, "error": errors, "pending": 0}
