"""In-process ring buffer for EventProvider consumer → Admin Event Bus / monitoring."""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any


class EventBusBuffer:
    """Short TTL ring buffer of consumed (or Memory-fanout) events."""

    def __init__(self, *, maxlen: int = 500) -> None:
        self._lock = threading.Lock()
        self._rows: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._total_seen = 0
        self._last_event_at: str | None = None
        self._by_type: dict[str, int] = {}
        self._source: str = "empty"  # consumed | outbox_fallback | empty

    def clear(self) -> None:
        with self._lock:
            self._rows.clear()
            self._total_seen = 0
            self._last_event_at = None
            self._by_type.clear()
            self._source = "empty"

    def append(
        self,
        *,
        topic: str,
        event: dict[str, Any],
        source: str = "consumed",
    ) -> None:
        occurred = event.get("occurred_at") or datetime.now(UTC).isoformat().replace("+00:00", "Z")
        event_type = str(event.get("event_type") or "unknown")
        event_id = str(event.get("event_id") or f"consumed-{self._total_seen}")
        row = {
            "id": event_id,
            "event_type": event_type,
            "topic": topic,
            "payload": event.get("payload") if isinstance(event.get("payload"), dict) else dict(event),
            "status": "consumed",
            "error": None,
            "correlation_id": event.get("correlation_id"),
            "created_at": occurred,
            "sent_at": occurred,
            "source": source,
            "envelope": {
                "event_id": event.get("event_id"),
                "producer": event.get("producer"),
                "occurred_at": occurred,
            },
        }
        with self._lock:
            if any(existing.get("id") == event_id for existing in self._rows):
                return
            self._rows.appendleft(row)
            self._total_seen += 1
            self._last_event_at = occurred
            self._by_type[event_type] = self._by_type.get(event_type, 0) + 1
            self._source = source

    def list(
        self,
        *,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            items = list(self._rows)
        total = len(items)
        sliced = items[offset : offset + limit]
        return sliced, total

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "buffered": len(self._rows),
                "total_seen": self._total_seen,
                "last_event_at": self._last_event_at,
                "by_type": dict(self._by_type),
                "source": self._source if self._rows else "empty",
            }


_buffer = EventBusBuffer()


def get_bus_buffer() -> EventBusBuffer:
    return _buffer


def reset_bus_buffer_for_tests() -> None:
    _buffer.clear()
