"""Chaos / failure simulator flags (FR-09)."""

from __future__ import annotations

from typing import Any

from app.providers.broker.mock import MockBrokerProvider
from app.providers.infrastructure.mock import MockInfrastructureProvider
from app.providers.manager import ProviderManager
from app.sim import flags as fault_flags


def list_faults() -> list[dict[str, Any]]:
    return fault_flags.list_faults()


def get_fault_history(*, limit: int = 25, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    return fault_flags.get_fault_history(limit=limit, offset=offset)


async def apply_faults_to_providers(providers: ProviderManager) -> None:
    """Push current fault flags onto mock provider instances (also mirrored live via flags)."""
    snapshot = {f["id"]: f for f in fault_flags.list_faults()}

    broker = await providers.get_broker_provider()
    if isinstance(broker, MockBrokerProvider):
        broker.clear_persistent_fault()
        active = fault_flags.active_broker_fault()
        if active:
            broker.set_persistent_fault(
                code=str(active["code"]),
                status=int(active.get("status", 503)),
                retryable=bool(active.get("retryable", True)),
            )

    infra = await providers.get_infrastructure_provider()
    if isinstance(infra, MockInfrastructureProvider):
        infra.set_probe_fail(bool(snapshot.get("infra_probe_fail", {}).get("enabled")))


async def set_fault(
    fault_id: str,
    *,
    enabled: bool,
    providers: ProviderManager,
) -> dict[str, Any]:
    row = fault_flags.set_enabled(fault_id, enabled=enabled)
    await apply_faults_to_providers(providers)
    return row


async def clear_all_faults(providers: ProviderManager) -> list[dict[str, Any]]:
    rows = fault_flags.clear_all()
    await apply_faults_to_providers(providers)
    return rows


def reset_sim_for_tests() -> None:
    fault_flags.reset_for_tests()
