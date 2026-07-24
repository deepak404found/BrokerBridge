"""Shared list pagination envelope (limit/offset, items+total)."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def clamp_limit(limit: int | None, *, default: int = DEFAULT_LIMIT, max_limit: int = MAX_LIMIT) -> int:
    if limit is None:
        return default
    return max(1, min(int(limit), max_limit))


def clamp_offset(offset: int | None) -> int:
    if offset is None:
        return 0
    return max(0, int(offset))


def next_offset(offset: int, limit: int, item_count: int, total: int) -> int | None:
    nxt = offset + item_count
    if nxt >= total or item_count == 0:
        return None
    return nxt


class PaginatedList(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=MAX_LIMIT)
    offset: int = Field(ge=0)
    next_offset: int | None = None

    @classmethod
    def build(
        cls,
        items: list[T],
        *,
        total: int,
        limit: int,
        offset: int,
    ) -> PaginatedList[T]:
        return cls(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            next_offset=next_offset(offset, limit, len(items), total),
        )


def pagination_example(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "items": [item],
        "total": 1,
        "limit": 25,
        "offset": 0,
        "next_offset": None,
    }
