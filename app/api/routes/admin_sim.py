"""Admin failure simulator endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import AUTH_ERRORS, success_response
from app.auth.deps import require_roles
from app.config.settings import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.events.outbox import drain_outbox, enqueue_outbox
from app.health.service import HealthService
from app.models.user import User
from app.providers.manager import get_provider_manager
from app.schemas.pagination import PaginatedList, clamp_limit, clamp_offset, pagination_example
from app.sim import service as sim

router = APIRouter(prefix="/api/v1/admin/sim", tags=["admin-sim"], responses=AUTH_ERRORS)


async def _emit_sim_event(
    db: AsyncSession,
    *,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Stage + drain a sim outbox event so Event Bus / Monitoring update immediately."""
    enqueue_outbox(db, event_type=event_type, topic="config", payload=payload)
    await db.commit()
    await drain_outbox(
        db,
        get_provider_manager(),
        limit=20,
        producer="brokerbridge-sim",
    )


class FaultToggleRequest(BaseModel):
    fault_id: str = Field(min_length=1, max_length=64)
    enabled: bool = True


_FAULT_EXAMPLE = {
    "id": "broker_unavailable",
    "label": "Mock broker unavailable (retryable)",
    "enabled": True,
    "target": "broker",
    "code": "BROKER_UNAVAILABLE",
    "status": 503,
}


@router.get(
    "/faults",
    summary="List simulator fault profiles",
    responses={200: success_response("Faults", example=[_FAULT_EXAMPLE])},
)
async def get_faults(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
) -> list[dict[str, Any]]:
    return sim.list_faults()


@router.post(
    "/faults",
    summary="Enable or disable a fault profile",
    responses={200: success_response("Updated fault", example=_FAULT_EXAMPLE)},
)
async def set_fault(
    body: FaultToggleRequest,
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    try:
        row = await sim.set_fault(
            body.fault_id,
            enabled=body.enabled,
            providers=get_provider_manager(),
        )
    except KeyError as exc:
        raise AppError("NOT_FOUND", f"Unknown fault_id: {body.fault_id}", status_code=404) from exc
    # Refresh broker health snapshots so Admin Health/Dashboard reflect active faults immediately
    if row.get("target") == "broker":
        await HealthService(db, settings, get_provider_manager()).probe_all()
    action = "enabled" if body.enabled else "disabled"
    await _emit_sim_event(
        db,
        event_type=f"sim.fault.{action}",
        payload={
            "fault_id": row["id"],
            "label": row.get("label"),
            "target": row.get("target"),
            "code": row.get("code"),
            "enabled": bool(row.get("enabled")),
            "action": action,
            "affects": row.get("affects"),
        },
    )
    return row


@router.post(
    "/faults/clear",
    summary="Disable all fault profiles",
    responses={200: success_response("Cleared", example=[_FAULT_EXAMPLE])},
)
async def clear_faults(
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[dict[str, Any]]:
    rows = await sim.clear_all_faults(get_provider_manager())
    await HealthService(db, settings, get_provider_manager()).probe_all()
    await _emit_sim_event(
        db,
        event_type="sim.fault.cleared",
        payload={"action": "cleared", "faults": [r["id"] for r in rows]},
    )
    return rows


@router.get(
    "/history",
    response_model=PaginatedList[dict[str, Any]],
    summary="Simulator toggle history",
    responses={
        200: success_response(
            "History",
            example=pagination_example(
                {"at": "2026-07-24T12:00:00Z", "action": "enable", "fault_id": "broker_unavailable"}
            ),
        )
    },
)
async def fault_history(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    limit: int = 25,
    offset: int = 0,
) -> PaginatedList[dict[str, Any]]:
    lim = clamp_limit(limit)
    off = clamp_offset(offset)
    items, total = sim.get_fault_history(limit=lim, offset=off)
    return PaginatedList.build(items, total=total, limit=lim, offset=off)
