"""Admin replay / recovery endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import AUTH_ERRORS, success_response
from app.auth.deps import require_roles
from app.config.settings import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.providers.manager import get_provider_manager
from app.replay.service import ReplayService, get_last_replay_status
from app.schemas.replay import ReplayRunResponse, ReplayStatusResponse

router = APIRouter(prefix="/api/v1/admin/replay", tags=["admin-replay"], responses=AUTH_ERRORS)

_RUN_EXAMPLE = {
    "ran_at": "2026-07-24T12:00:00Z",
    "scanned": 2,
    "retried": 1,
    "recovered": 1,
    "skipped": 1,
    "failed": 0,
    "details": [
        {
            "order_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "result": "recovered",
            "reason": "resubmit",
            "status": "SUBMITTED",
        }
    ],
}


@router.post(
    "/run",
    response_model=ReplayRunResponse,
    summary="Run recovery scan for stuck / INDOUBT orders",
    responses={200: success_response("Replay result", example=_RUN_EXAMPLE)},
)
async def run_replay(
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    return await ReplayService(db, settings, get_provider_manager()).run(limit=limit)


@router.get(
    "/status",
    response_model=ReplayStatusResponse,
    summary="Last replay run summary",
    responses={
        200: success_response(
            "Replay status",
            example={
                "ran_at": None,
                "scanned": 0,
                "retried": 0,
                "recovered": 0,
                "skipped": 0,
                "failed": 0,
                "auto_scan_on_startup": False,
            },
        )
    },
)
async def replay_status(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
) -> dict[str, Any]:
    status = get_last_replay_status()
    status["auto_scan_on_startup"] = False
    return status
