from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import AUTH_ERRORS, NOT_FOUND, UNPROCESSABLE, success_response
from app.auth.deps import require_roles
from app.broker.service import BrokerService
from app.config.settings import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.providers.manager import get_provider_manager
from app.schemas.brokers import (
    BrokerCreateRequest,
    BrokerPatchRequest,
    BrokerResponse,
    SessionStatusResponse,
)
from app.sessions.service import SessionService

router = APIRouter(prefix="/api/v1/brokers", tags=["brokers"], responses=AUTH_ERRORS)

_BROKER_EXAMPLE = {
    "id": "11111111-1111-4111-8111-111111111111",
    "client_id": "22222222-2222-4222-8222-222222222222",
    "provider_type": "mock",
    "display_name": "Mock Alpha Broker",
    "priority": 10,
    "enabled": True,
    "allowed_regions": ["ewr", "ord"],
    "capabilities": {
        "asset_classes": ["equities"],
        "order_types": ["MARKET", "LIMIT"],
        "supports_whitelist": True,
    },
    "rate_limit_rps": 50.0,
    "created_at": "2026-07-24T10:00:00Z",
    "updated_at": "2026-07-24T10:00:00Z",
}

_BROKER_CREATE_EXAMPLE = {
    "client_id": "22222222-2222-4222-8222-222222222222",
    "provider_type": "mock",
    "display_name": "Mock Gamma Broker",
    "priority": 30,
    "enabled": True,
    "allowed_regions": ["ewr"],
    "credentials": {"api_key": "mock-key", "api_secret": "mock-secret"},
    "rate_limit_rps": 40,
}

_SESSION_EXAMPLE = {
    "broker_account_id": "11111111-1111-4111-8111-111111111111",
    "broker_display_name": "Mock Alpha Broker",
    "status": "valid",
    "expires_at": "2026-07-24T11:00:00Z",
    "updated_at": "2026-07-24T10:00:00Z",
    "has_tokens": True,
}


def _broker_svc(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BrokerService:
    return BrokerService(db, settings, get_provider_manager())


def _session_svc(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionService:
    return SessionService(db, settings, get_provider_manager())


@router.post(
    "",
    response_model=BrokerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard broker account",
    responses={
        201: success_response("Broker created", example=_BROKER_EXAMPLE),
        **UNPROCESSABLE,
    },
)
async def create_broker(
    body: Annotated[
        BrokerCreateRequest,
        Body(openapi_examples={"default": {"summary": "Onboard mock broker", "value": _BROKER_CREATE_EXAMPLE}}),
    ],
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[BrokerService, Depends(_broker_svc)],
) -> BrokerResponse:
    row = await svc.create(
        client_id=body.client_id,
        provider_type=body.provider_type,
        display_name=body.display_name,
        credentials=body.credentials,
        priority=body.priority,
        allowed_regions=body.allowed_regions,
        rate_limit_rps=body.rate_limit_rps,
        enabled=body.enabled,
    )
    return BrokerResponse.model_validate(row)


@router.get(
    "",
    response_model=list[BrokerResponse],
    summary="List broker accounts",
    responses={200: success_response("Broker list", example=[_BROKER_EXAMPLE])},
)
async def list_brokers(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    svc: Annotated[BrokerService, Depends(_broker_svc)],
) -> list[BrokerResponse]:
    rows = await svc.list()
    return [BrokerResponse.model_validate(r) for r in rows]


@router.get(
    "/{broker_id}",
    response_model=BrokerResponse,
    summary="Broker detail + capabilities",
    responses={200: success_response("Broker detail", example=_BROKER_EXAMPLE), **NOT_FOUND},
)
async def get_broker(
    broker_id: UUID,
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    svc: Annotated[BrokerService, Depends(_broker_svc)],
) -> BrokerResponse:
    return BrokerResponse.model_validate(await svc.get(broker_id))


@router.patch(
    "/{broker_id}",
    response_model=BrokerResponse,
    summary="Enable/disable, priority, limits",
    responses={200: success_response("Broker updated", example=_BROKER_EXAMPLE), **NOT_FOUND},
)
async def patch_broker(
    broker_id: UUID,
    body: BrokerPatchRequest,
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[BrokerService, Depends(_broker_svc)],
) -> BrokerResponse:
    row = await svc.patch(
        broker_id,
        enabled=body.enabled,
        priority=body.priority,
        display_name=body.display_name,
        rate_limit_rps=body.rate_limit_rps,
        allowed_regions=body.allowed_regions,
    )
    return BrokerResponse.model_validate(row)


@router.post(
    "/{broker_id}/capabilities/refresh",
    response_model=BrokerResponse,
    summary="Refresh broker capabilities",
    responses={200: success_response("Capabilities refreshed", example=_BROKER_EXAMPLE), **NOT_FOUND},
)
async def refresh_capabilities(
    broker_id: UUID,
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
    svc: Annotated[BrokerService, Depends(_broker_svc)],
) -> BrokerResponse:
    return BrokerResponse.model_validate(await svc.refresh_capabilities(broker_id))


@router.get(
    "/{broker_id}/sessions",
    response_model=SessionStatusResponse,
    summary="Session status for broker",
    responses={200: success_response("Session status", example=_SESSION_EXAMPLE), **NOT_FOUND},
)
async def get_broker_session(
    broker_id: UUID,
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    brokers: Annotated[BrokerService, Depends(_broker_svc)],
    sessions: Annotated[SessionService, Depends(_session_svc)],
) -> SessionStatusResponse:
    broker = await brokers.get(broker_id)
    sess = await sessions.get_for_broker(broker_id)
    if sess is None:
        return SessionStatusResponse(
            broker_account_id=broker_id,
            broker_display_name=broker.display_name,
            status="missing",
            has_tokens=False,
        )
    return SessionStatusResponse(
        broker_account_id=broker_id,
        broker_display_name=broker.display_name,
        status=sess.status,
        expires_at=sess.expires_at,
        updated_at=sess.updated_at,
        has_tokens=bool(sess.access_token_encrypted),
    )


@router.post(
    "/{broker_id}/sessions/ensure",
    response_model=SessionStatusResponse,
    summary="Ensure/refresh broker session",
    responses={200: success_response("Session ensured", example=_SESSION_EXAMPLE), **NOT_FOUND},
)
async def ensure_broker_session(
    broker_id: UUID,
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
    brokers: Annotated[BrokerService, Depends(_broker_svc)],
    sessions: Annotated[SessionService, Depends(_session_svc)],
    force_refresh: bool = False,
) -> SessionStatusResponse:
    broker = await brokers.get(broker_id)
    sess = await sessions.ensure(broker_id, force_refresh=force_refresh)
    return SessionStatusResponse(
        broker_account_id=broker_id,
        broker_display_name=broker.display_name,
        status=sess.status,
        expires_at=sess.expires_at,
        updated_at=sess.updated_at,
        has_tokens=bool(sess.access_token_encrypted),
    )
