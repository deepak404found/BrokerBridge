"""In-process chaos fault flags (FR-09).

Kept free of provider imports so mock adapters can read live state at call time
(survives ProviderManager cache invalidation).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

_lock = threading.Lock()
_faults: dict[str, dict[str, Any]] = {
    "broker_unavailable": {
        "id": "broker_unavailable",
        "label": "Mock broker unavailable (retryable)",
        "enabled": False,
        "target": "broker",
        "code": "BROKER_UNAVAILABLE",
        "status": 503,
        "retryable": True,
        "affects": "place_order, probe → Broker Health / routing failover",
    },
    "broker_reject": {
        "id": "broker_reject",
        "label": "Mock broker hard reject (non-retryable)",
        "enabled": False,
        "target": "broker",
        "code": "BROKER_REJECT",
        "status": 400,
        "retryable": False,
        "affects": "place_order (non-retryable) + probe → Orders fail, Health degrades",
    },
    "infra_probe_fail": {
        "id": "infra_probe_fail",
        "label": "Infrastructure probe failure",
        "enabled": False,
        "target": "infra",
        "code": "INFRA_UNAVAILABLE",
        "status": 503,
        "affects": "infra.probe, create_ip / allocate → Static IP allocation fails",
    },
}
_history: list[dict[str, Any]] = []


def list_faults() -> list[dict[str, Any]]:
    with _lock:
        return [dict(v) for v in _faults.values()]


def is_enabled(fault_id: str) -> bool:
    with _lock:
        row = _faults.get(fault_id)
        return bool(row and row.get("enabled"))


def active_broker_fault() -> dict[str, Any] | None:
    """Return the enabled broker fault profile, if any (mutual exclusion)."""
    with _lock:
        for key in ("broker_unavailable", "broker_reject"):
            row = _faults.get(key)
            if row and row.get("enabled"):
                return dict(row)
    return None


def infra_fault_enabled() -> bool:
    return is_enabled("infra_probe_fail")


def get_fault_history(*, limit: int = 25, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    with _lock:
        items = list(reversed(_history))
    total = len(items)
    return items[offset : offset + limit], total


def record(action: str, fault_id: str, **extra: Any) -> None:
    with _lock:
        _history.append(
            {
                "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "action": action,
                "fault_id": fault_id,
                **extra,
            }
        )
        if len(_history) > 200:
            del _history[:-200]


def set_enabled(fault_id: str, *, enabled: bool) -> dict[str, Any]:
    with _lock:
        if fault_id not in _faults:
            raise KeyError(fault_id)
        if enabled and fault_id in {"broker_unavailable", "broker_reject"}:
            for other in ("broker_unavailable", "broker_reject"):
                if other != fault_id:
                    _faults[other]["enabled"] = False
        _faults[fault_id]["enabled"] = bool(enabled)
        row = dict(_faults[fault_id])
    record("enable" if enabled else "disable", fault_id)
    return row


def clear_all() -> list[dict[str, Any]]:
    with _lock:
        for row in _faults.values():
            if row["enabled"]:
                _history.append(
                    {
                        "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                        "action": "disable",
                        "fault_id": row["id"],
                    }
                )
            row["enabled"] = False
        if len(_history) > 200:
            del _history[:-200]
    return list_faults()


def reset_for_tests() -> None:
    with _lock:
        for row in _faults.values():
            row["enabled"] = False
        _history.clear()
