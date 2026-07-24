import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import AUTH_ERRORS, NOT_FOUND, success_response
from app.auth.deps import require_roles
from app.config.settings import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.orders.service import OrderService
from app.providers.manager import get_provider_manager
from app.schemas.orders import OrderListResponse, OrderPlaceRequest, OrderResponse

router = APIRouter(prefix="/api/v1/orders", tags=["orders"], responses=AUTH_ERRORS)

_ORDER_EXAMPLE: dict[str, Any] = {
    "id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "client_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "client_order_id": "c-10001",
    "side": "BUY",
    "symbol": "AAPL",
    "quantity": "10",
    "order_type": "MARKET",
    "time_in_force": "DAY",
    "status": "SUBMITTED",
    "broker_account_id": "11111111-1111-4111-8111-111111111111",
    "static_ip_id": "22222222-2222-4222-8222-222222222222",
    "preferred_broker_id": None,
    "region_preference": "ewr",
    "broker_order_id": "mock-a1b2c3d4",
    "error_code": None,
    "created_at": "2026-07-24T12:00:00Z",
    "updated_at": "2026-07-24T12:00:01Z",
}

_PLACE_EXAMPLE = {
    "client_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "client_order_id": "c-10001",
    "symbol": "AAPL",
    "quantity": 10,
    "order_type": "MARKET",
    "time_in_force": "DAY",
    "preferred_broker_id": None,
    "region_preference": "ewr",
}


def _svc(db: AsyncSession, settings: Settings) -> OrderService:
    return OrderService(db, settings, get_provider_manager())


def _to_response(order) -> OrderResponse:
    return OrderResponse.model_validate(order)


@router.post(
    "/buy",
    response_model=OrderResponse,
    summary="Place buy order (inline Mode B)",
    responses={
        201: success_response("Order created/submitted", example=_ORDER_EXAMPLE),
        200: success_response("Idempotent replay", example=_ORDER_EXAMPLE),
        **NOT_FOUND,
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": _PLACE_EXAMPLE,
                }
            }
        }
    },
)
async def buy_order(
    body: OrderPlaceRequest,
    response: Response,
    _: Annotated[User, Depends(require_roles("admin", "ops", "client"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OrderResponse:
    order, created = await _svc(db, settings).place(
        client_id=body.client_id,
        client_order_id=body.client_order_id,
        side="BUY",
        symbol=body.symbol,
        quantity=body.quantity,
        order_type=body.order_type,
        time_in_force=body.time_in_force,
        preferred_broker_id=body.preferred_broker_id,
        region_preference=body.region_preference,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _to_response(order)


@router.post(
    "/sell",
    response_model=OrderResponse,
    summary="Place sell order (inline Mode B)",
    responses={
        201: success_response("Order created/submitted", example={**_ORDER_EXAMPLE, "side": "SELL"}),
        200: success_response("Idempotent replay", example={**_ORDER_EXAMPLE, "side": "SELL"}),
        **NOT_FOUND,
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {**_PLACE_EXAMPLE, "client_order_id": "c-10002"},
                }
            }
        }
    },
)
async def sell_order(
    body: OrderPlaceRequest,
    response: Response,
    _: Annotated[User, Depends(require_roles("admin", "ops", "client"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OrderResponse:
    order, created = await _svc(db, settings).place(
        client_id=body.client_id,
        client_order_id=body.client_order_id,
        side="SELL",
        symbol=body.symbol,
        quantity=body.quantity,
        order_type=body.order_type,
        time_in_force=body.time_in_force,
        preferred_broker_id=body.preferred_broker_id,
        region_preference=body.region_preference,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _to_response(order)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    summary="Cancel order",
    responses={
        200: success_response("Cancelled", example={**_ORDER_EXAMPLE, "status": "CANCELLED"}),
        **NOT_FOUND,
    },
)
async def cancel_order(
    order_id: uuid.UUID,
    _: Annotated[User, Depends(require_roles("admin", "ops", "client"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OrderResponse:
    order = await _svc(db, settings).cancel(order_id)
    return _to_response(order)


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get order status",
    responses={200: success_response("Order", example=_ORDER_EXAMPLE), **NOT_FOUND},
)
async def get_order(
    order_id: uuid.UUID,
    _: Annotated[User, Depends(require_roles("admin", "ops", "client", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OrderResponse:
    order = await _svc(db, settings).get(order_id)
    return _to_response(order)


@router.get(
    "",
    response_model=OrderListResponse,
    summary="Order history",
    responses={
        200: success_response(
            "Orders",
            example={
                "items": [_ORDER_EXAMPLE],
                "total": 1,
                "limit": 25,
                "offset": 0,
                "next_offset": None,
            },
        )
    },
)
async def list_orders(
    _: Annotated[User, Depends(require_roles("admin", "ops", "client", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    client_id: uuid.UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    symbol: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> OrderListResponse:
    items, total = await _svc(db, settings).list_orders(
        client_id=client_id,
        status=status_filter,
        symbol=symbol,
        limit=limit,
        offset=offset,
    )
    nxt = offset + len(items)
    return OrderListResponse(
        items=[_to_response(o) for o in items],
        total=total,
        limit=limit,
        offset=offset,
        next_offset=None if nxt >= total or not items else nxt,
    )
