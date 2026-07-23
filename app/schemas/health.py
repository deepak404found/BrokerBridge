from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CheckResult(BaseModel):
    """Result of a single dependency readiness probe."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"status": "ok", "latency_ms": 2.4, "detail": None},
            ]
        }
    )

    status: Literal["ok", "fail", "skipped"] = Field(
        description="Probe outcome for this dependency",
        examples=["ok"],
    )
    latency_ms: float | None = Field(
        default=None,
        description="Round-trip latency in milliseconds, if measured",
        examples=[2.4],
    )
    detail: str | None = Field(
        default=None,
        description="Optional human-readable failure or skip reason",
        examples=[None],
    )


class ReadyChecks(BaseModel):
    """Critical Local Lab dependency checks."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "postgres": {"status": "ok", "latency_ms": 2.4, "detail": None},
                    "redis": {"status": "ok", "latency_ms": 0.8, "detail": None},
                    "redpanda": {"status": "ok", "latency_ms": 1.1, "detail": None},
                }
            ]
        }
    )

    postgres: CheckResult
    redis: CheckResult
    redpanda: CheckResult


class LiveResponse(BaseModel):
    """Liveness: process is up (no dependency checks)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})

    status: Literal["ok"] = Field(default="ok", examples=["ok"])


class ReadyResponse(BaseModel):
    """Readiness: whether the API can accept traffic."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "checks": {
                        "postgres": {"status": "ok", "latency_ms": 2.4, "detail": None},
                        "redis": {"status": "ok", "latency_ms": 0.8, "detail": None},
                        "redpanda": {"status": "ok", "latency_ms": 1.1, "detail": None},
                    },
                }
            ]
        }
    )

    status: Literal["ok", "not_ready"] = Field(
        description="ok when all critical checks pass; not_ready otherwise",
        examples=["ok"],
    )
    checks: ReadyChecks
