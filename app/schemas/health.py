from typing import Literal

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    """Result of a single dependency readiness probe."""

    status: Literal["ok", "fail", "skipped"] = Field(
        description="Probe outcome for this dependency",
    )
    latency_ms: float | None = Field(
        default=None,
        description="Round-trip latency in milliseconds, if measured",
    )
    detail: str | None = Field(
        default=None,
        description="Optional human-readable failure or skip reason",
    )


class ReadyChecks(BaseModel):
    """Critical Local Lab dependency checks."""

    postgres: CheckResult
    redis: CheckResult
    redpanda: CheckResult


class LiveResponse(BaseModel):
    """Liveness: process is up (no dependency checks)."""

    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    """Readiness: whether the API can accept traffic."""

    status: Literal["ok", "not_ready"] = Field(
        description="ok when all critical checks pass; not_ready otherwise",
    )
    checks: ReadyChecks
