"""Documentation-range IP helpers for mock infrastructure backends."""

from __future__ import annotations

import itertools
from uuid import uuid4


class DocNetIpAllocator:
    """Allocate addresses from 198.51.100.0/24 and 203.0.113.0/24 (DOC-NET)."""

    def __init__(self) -> None:
        self._counter = itertools.count(1)

    def next_address(self, *, used: set[str] | None = None) -> str:
        used = used or set()
        for _ in range(64):
            n = next(self._counter)
            salt = int(uuid4().hex[:8], 16)
            host = ((n + salt) % 254) + 1
            if (n + salt) % 2 == 0:
                candidate = f"203.0.113.{host}"
            else:
                candidate = f"198.51.100.{host}"
            if candidate not in used:
                return candidate
        # Extremely unlikely exhaustion fallback
        return f"198.51.100.{(next(self._counter) % 254) + 1}"
