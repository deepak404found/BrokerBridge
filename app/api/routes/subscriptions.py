from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import AUTH_ERRORS, NOT_FOUND, UNPROCESSABLE, success_response
from app.auth.deps import require_roles
from app.config.settings import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.providers.manager import get_provider_manager
from app.schemas.pagination import PaginatedList, pagination_example
from app.schemas.subscriptions import (
    EnforceExpiryResponse,
    SubscriptionCreateRequest,
    SubscriptionResponse,
)
from app.subscriptions.service import SubscriptionService

router = APIRouter(
    prefix="/api/v1/subscriptions",
    tags=["subscriptions"],
    responses=AUTH_ERRORS,
)

_SUB_EXAMPLE = {
    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "client_id": "22222222-2222-4222-8222-222222222222",
    "status": "active",
    "starts_at": "2026-01-01T00:00:00Z",
    "ends_at": "2026-12-31T23:59:59Z",
    "teardown_mode": "SUSPEND",
    "teardown_completed_at": None,
    "created_at": "2026-01-01T00:00:00Z",
}


def _svc(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SubscriptionService:
    return SubscriptionService(db, settings, get_provider_manager())


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create client subscription",
    responses={201: success_response("Created", example=_SUB_EXAMPLE), **UNPROCESSABLE},
)
async def create_subscription(
    body: SubscriptionCreateRequest,
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[SubscriptionService, Depends(_svc)],
) -> SubscriptionResponse:
    row = await svc.create(
        client_id=body.client_id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        teardown_mode=body.teardown_mode,
    )
    return SubscriptionResponse.model_validate(row)


@router.get(
    "",
    response_model=PaginatedList[SubscriptionResponse],
    summary="List subscriptions",
    responses={200: success_response("List", example=pagination_example(_SUB_EXAMPLE))},
)
async def list_subscriptions(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    svc: Annotated[SubscriptionService, Depends(_svc)],
    client_id: UUID | None = Query(default=None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedList[SubscriptionResponse]:
    rows, total = await svc.list(client_id=client_id, limit=limit, offset=offset)
    return PaginatedList.build(
        [SubscriptionResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/enforce-expiry",
    response_model=EnforceExpiryResponse,
    summary="Enforce subscription expiry teardown (BR-G07)",
)
async def enforce_expiry(
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
    svc: Annotated[SubscriptionService, Depends(_svc)],
) -> EnforceExpiryResponse:
    stats = await svc.enforce_expiry()
    return EnforceExpiryResponse(**stats)


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    summary="Get subscription",
    responses={**NOT_FOUND},
)
async def get_subscription(
    subscription_id: UUID,
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    svc: Annotated[SubscriptionService, Depends(_svc)],
) -> SubscriptionResponse:
    return SubscriptionResponse.model_validate(await svc.get(subscription_id))


@router.post(
    "/{subscription_id}/expire",
    response_model=SubscriptionResponse,
    summary="Force-expire a subscription (demo / Admin)",
    responses={**NOT_FOUND},
)
async def expire_subscription(
    subscription_id: UUID,
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[SubscriptionService, Depends(_svc)],
) -> SubscriptionResponse:
    row = await svc.expire_now(subscription_id)
    return SubscriptionResponse.model_validate(row)
