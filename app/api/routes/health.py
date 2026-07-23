from fastapi import APIRouter, Response

from app.api.openapi import LIVE_SUCCESS, READY_RESPONSES
from app.config.settings import get_settings
from app.core.health_checks import run_readiness_checks
from app.schemas.health import LiveResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health/live",
    response_model=LiveResponse,
    summary="Liveness probe",
    description="Process is up. Does not check dependencies.",
    responses=LIVE_SUCCESS,
)
async def live() -> LiveResponse:
    return LiveResponse(status="ok")


@router.get(
    "/health/ready",
    response_model=ReadyResponse,
    summary="Readiness probe",
    description=(
        "TCP connectivity to Postgres, Redis, and Redpanda using configured URLs. "
        "Returns 200 when all critical checks pass; 503 when any check fails."
    ),
    responses=READY_RESPONSES,
)
async def ready(response: Response) -> ReadyResponse:
    settings = get_settings()
    result = await run_readiness_checks(settings)
    if result.status != "ok":
        response.status_code = 503
    return result
