from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any


def build_envelope(
    event_type: str,
    payload: dict[str, Any],
    *,
    producer: str = "brokerbridge-api",
    correlation_id: str | None = None,
    event_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "producer": producer,
        "correlation_id": correlation_id,
        "payload": payload,
    }


DEFAULT_TOPIC_MAP = {
    "orders": "brokerbridge.orders",
    "brokers": "brokerbridge.brokers",
    "ip": "brokerbridge.ip",
    "subscriptions": "brokerbridge.subscriptions",
    "config": "brokerbridge.config",
}


def resolve_physical_topic(
    logical: str,
    *,
    topic_prefix: str | None = None,
    topic_map: dict[str, str] | None = None,
) -> str:
    merged = dict(DEFAULT_TOPIC_MAP)
    if topic_map:
        merged.update({str(k): str(v) for k, v in topic_map.items()})
    if logical in merged:
        physical = merged[logical]
    elif topic_prefix:
        physical = f"{topic_prefix.rstrip('.')}.{logical}"
    else:
        physical = f"brokerbridge.{logical}"
    if topic_prefix and logical not in (topic_map or {}) and physical.startswith("brokerbridge."):
        # Allow prefix override of default brokerbridge.* names
        suffix = physical.split(".", 1)[-1]
        physical = f"{topic_prefix.rstrip('.')}.{suffix}"
    return physical
