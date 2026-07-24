from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import AUTH_ERRORS, success_response
from app.auth.deps import require_roles
from app.config.settings import Settings, get_settings
from app.db.session import get_db
from app.events.outbox import drain_outbox, list_outbox
from app.health.service import HealthService
from app.models.user import User
from app.orders.service import OrderService
from app.providers.manager import get_provider_manager
from app.rate_limit.service import RateLimitService
from app.routing.engine import RoutingEngine
from app.schemas.brokers import SessionStatusResponse
from app.schemas.events import OutboxDrainResponse, OutboxEventResponse
from app.schemas.monitoring_w3 import (
    FailoverEventResponse,
    HealthBrokerResponse,
    OrdersEngineResponse,
    RateLimitSnapshotResponse,
    RoutingPreviewRequest,
    RoutingPreviewResponse,
)
from app.sessions.service import SessionService

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"], responses=AUTH_ERRORS)

_SESSION_EXAMPLE = {
    "broker_account_id": "11111111-1111-4111-8111-111111111111",
    "broker_display_name": "Mock Alpha Broker",
    "status": "valid",
    "expires_at": "2026-07-24T11:00:00Z",
    "updated_at": "2026-07-24T10:00:00Z",
    "has_tokens": True,
}

_HEALTH_EXAMPLE: dict[str, Any] = {
    "broker_account_id": "11111111-1111-4111-8111-111111111111",
    "broker_display_name": "Mock Alpha Broker",
    "enabled": True,
    "latency_ms": 2.4,
    "success_rate": 1.0,
    "timeout_rate": 0.0,
    "connectivity": True,
    "ip_health": 100.0,
    "score": 97.5,
    "status": "healthy",
    "measured_at": "2026-07-24T12:00:00Z",
    "breakdown": {
        "latency_ms": 2.4,
        "success_rate": 1.0,
        "timeout_rate": 0.0,
        "connectivity": True,
        "ip_health": 100.0,
    },
}

_RATE_EXAMPLE = {
    "broker_account_id": "11111111-1111-4111-8111-111111111111",
    "broker_display_name": "Mock Alpha Broker",
    "limit_rps": 50.0,
    "used": 3.0,
    "remaining": 47.0,
    "pressure": 1.2,
    "window_seconds": 1.0,
}


@router.get(
    "/sessions",
    response_model=list[SessionStatusResponse],
    summary="List broker session statuses",
    responses={200: success_response("Sessions", example=[_SESSION_EXAMPLE])},
)
async def list_sessions(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[SessionStatusResponse]:
    svc = SessionService(db, settings, get_provider_manager())
    rows = await svc.list_all()
    return [
        SessionStatusResponse(
            broker_account_id=sess.broker_account_id,
            broker_display_name=broker.display_name,
            status=sess.status,
            expires_at=sess.expires_at,
            updated_at=sess.updated_at,
            has_tokens=bool(sess.access_token_encrypted),
        )
        for sess, broker in rows
    ]


@router.get(
    "/brokers/health",
    response_model=list[HealthBrokerResponse],
    summary="Latest broker health scores",
    responses={200: success_response("Health", example=[_HEALTH_EXAMPLE])},
)
async def list_broker_health(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[HealthBrokerResponse]:
    rows = await HealthService(db, settings, get_provider_manager()).latest_for_brokers()
    return [HealthBrokerResponse.model_validate(r) for r in rows]


@router.post(
    "/brokers/health/probe",
    response_model=list[HealthBrokerResponse],
    summary="Probe all enabled brokers and refresh health snapshots",
    responses={200: success_response("Probed health", example=[_HEALTH_EXAMPLE])},
)
async def probe_broker_health(
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[HealthBrokerResponse]:
    svc = HealthService(db, settings, get_provider_manager())
    await svc.probe_all()
    rows = await svc.latest_for_brokers(probe_if_empty=False)
    return [HealthBrokerResponse.model_validate(r) for r in rows]


@router.get(
    "/rate-limits",
    response_model=list[RateLimitSnapshotResponse],
    summary="Rate-limit quotas and pressure",
    responses={200: success_response("Rate limits", example=[_RATE_EXAMPLE])},
)
async def list_rate_limits(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[RateLimitSnapshotResponse]:
    rows = await RateLimitService(db, settings, get_provider_manager()).list_snapshots()
    return [RateLimitSnapshotResponse.model_validate(r) for r in rows]


@router.get(
    "/failovers",
    response_model=list[FailoverEventResponse],
    summary="Recent failover events",
    responses={
        200: success_response(
            "Failovers",
            example=[
                {
                    "id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                    "order_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                    "from_broker_id": "11111111-1111-4111-8111-111111111111",
                    "to_broker_id": "33333333-3333-4333-8333-333333333333",
                    "reason": "BROKER_UNAVAILABLE",
                    "details": {"status": 503},
                    "created_at": "2026-07-24T12:01:00Z",
                }
            ],
        )
    },
)
async def list_failovers(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(50, ge=1, le=200),
) -> list[FailoverEventResponse]:
    rows = await OrderService(db, settings, get_provider_manager()).list_failovers(limit=limit)
    return [FailoverEventResponse.model_validate(r) for r in rows]


@router.get(
    "/orders/engine",
    response_model=OrdersEngineResponse,
    summary="Order engine inflight and status counts",
    responses={
        200: success_response(
            "Engine stats",
            example={
                "inflight": 0,
                "max_inflight": 100,
                "by_status": {"SUBMITTED": 3, "CANCELLED": 1},
                "execution_mode": "inline",
            },
        )
    },
)
async def orders_engine(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OrdersEngineResponse:
    stats = await OrderService(db, settings, get_provider_manager()).engine_stats()
    return OrdersEngineResponse.model_validate(stats)


@router.post(
    "/routing/preview",
    response_model=RoutingPreviewResponse,
    summary="Preview smart routing candidate matrix",
    responses={
        200: success_response(
            "Routing preview",
            example={
                "require_assigned_ip": True,
                "primary": {
                    "broker_account_id": "11111111-1111-4111-8111-111111111111",
                    "broker_display_name": "Mock Alpha Broker",
                    "route_score": 117.5,
                    "health_score": 97.5,
                    "health_status": "healthy",
                    "rate_pressure": 0.0,
                    "static_ip_id": "22222222-2222-4222-8222-222222222222",
                    "reasons": [],
                },
                "chain": [],
                "excluded": [],
            },
        )
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "client_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                        "preferred_broker_id": None,
                        "region_preference": "ewr",
                    }
                }
            }
        }
    },
)
async def routing_preview(
    body: RoutingPreviewRequest,
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RoutingPreviewResponse:
    preview = await RoutingEngine(db, settings, get_provider_manager()).preview(
        client_id=body.client_id,
        preferred_broker_id=body.preferred_broker_id,
        region_preference=body.region_preference,
    )
    return RoutingPreviewResponse.model_validate(preview)


@router.get(
    "/events",
    response_model=list[OutboxEventResponse],
    summary="Recent outbox / event bus rows",
    responses={
        200: success_response(
            "Events",
            example=[
                {
                    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "event_type": "ip.rotated",
                    "topic": "ip",
                    "payload": {"old_ip": "198.51.100.10", "new_ip": "198.51.100.22"},
                    "status": "sent",
                    "error": None,
                    "correlation_id": None,
                    "created_at": "2026-07-24T12:00:00Z",
                    "sent_at": "2026-07-24T12:00:01Z",
                }
            ],
        )
    },
)
async def list_events(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
    status: str | None = Query(default=None, description="pending|sent|error"),
) -> list[OutboxEventResponse]:
    rows = await list_outbox(db, limit=limit, status=status)
    return [OutboxEventResponse.model_validate(r) for r in rows]


@router.post(
    "/events/drain",
    response_model=OutboxDrainResponse,
    summary="Drain pending outbox to EventProvider (lab/ops)",
)
async def drain_events(
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
) -> OutboxDrainResponse:
    stats = await drain_outbox(db, get_provider_manager(), limit=limit, producer="brokerbridge-api")
    return OutboxDrainResponse.model_validate(stats)