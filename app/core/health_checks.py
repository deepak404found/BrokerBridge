"""Lightweight readiness probes (TCP connect) for Local Lab dependencies."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from app.config.settings import Settings
from app.schemas.health import CheckResult, ReadyChecks, ReadyResponse

DEFAULT_TIMEOUT_S = 2.0


def _host_port_from_url(url: str, *, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or default_port
    return host, port


def _host_port_from_brokers(brokers: str) -> tuple[str, int]:
    first = brokers.split(",")[0].strip()
    if "://" in first:
        return _host_port_from_url(first, default_port=9092)
    host, sep, port_s = first.partition(":")
    if not sep or not port_s.isdigit():
        return host or "localhost", 9092
    return host or "localhost", int(port_s)


async def tcp_check(host: str, port: int, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> CheckResult:
    started = time.perf_counter()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_s,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 — close best-effort
            pass
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return CheckResult(status="ok", latency_ms=latency_ms, detail=None)
    except Exception as exc:  # noqa: BLE001 — surface as check failure
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        detail = f"{type(exc).__name__}: {exc}"[:200]
        return CheckResult(status="fail", latency_ms=latency_ms, detail=detail)


async def run_readiness_checks(settings: Settings) -> ReadyResponse:
    pg_host, pg_port = _host_port_from_url(settings.database_url, default_port=5432)
    redis_host, redis_port = _host_port_from_url(settings.redis_url, default_port=6379)
    rp_host, rp_port = _host_port_from_brokers(settings.redpanda_brokers)

    postgres, redis, redpanda = await asyncio.gather(
        tcp_check(pg_host, pg_port),
        tcp_check(redis_host, redis_port),
        tcp_check(rp_host, rp_port),
    )
    checks = ReadyChecks(postgres=postgres, redis=redis, redpanda=redpanda)
    all_ok = all(c.status == "ok" for c in (postgres, redis, redpanda))
    return ReadyResponse(status="ok" if all_ok else "not_ready", checks=checks)
