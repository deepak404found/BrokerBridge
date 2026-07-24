from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReplayRunResponse(BaseModel):
    ran_at: str | None = None
    scanned: int = 0
    retried: int = 0
    recovered: int = 0
    skipped: int = 0
    failed: int = 0
    details: list[dict[str, Any]] = Field(default_factory=list)


class ReplayStatusResponse(BaseModel):
    ran_at: str | None = None
    scanned: int = 0
    retried: int = 0
    recovered: int = 0
    skipped: int = 0
    failed: int = 0
    detail_count: int | None = None
    auto_scan_on_startup: bool = False
