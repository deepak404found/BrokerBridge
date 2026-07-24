from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import AUTH_ERRORS, NOT_FOUND, success_response
from app.auth.deps import require_roles
from app.config.service import ConfigService
from app.db.session import get_db
from app.events.outbox import enqueue_outbox
from app.models.user import User
from app.schemas.config import ConfigItemResponse, ConfigPutRequest

router = APIRouter(prefix="/api/v1/admin/config", tags=["admin"], responses=AUTH_ERRORS)

_WEIGHTS_EXAMPLE: dict[str, Any] = {
    "key": "routing.weights",
    "value": {"w_lat": 0.25, "w_succ": 0.30, "w_conn": 0.15, "w_to": 0.20, "w_ip": 0.10},
    "version": 1,
    "updated_by": None,
    "updated_at": "2026-07-24T12:00:00Z",
}


@router.get(
    "",
    response_model=list[ConfigItemResponse],
    summary="List configuration items",
    responses={200: success_response("Config list", example=[_WEIGHTS_EXAMPLE])},
)
async def list_config(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    prefix: str | None = Query(None, description="Optional key prefix filter"),
) -> list[ConfigItemResponse]:
    rows = await ConfigService(db).list_items(prefix=prefix)
    return [ConfigItemResponse.model_validate(r) for r in rows]


@router.get(
    "/{key}",
    response_model=ConfigItemResponse,
    summary="Get configuration item",
    responses={200: success_response("Config item", example=_WEIGHTS_EXAMPLE), **NOT_FOUND},
)
async def get_config(
    key: str,
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConfigItemResponse:
    item = await ConfigService(db).get(key)
    return ConfigItemResponse.model_validate(item)


@router.put(
    "/{key}",
    response_model=ConfigItemResponse,
    summary="Update configuration item",
    responses={200: success_response("Updated config", example=_WEIGHTS_EXAMPLE), **NOT_FOUND},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "example": {
                        "value": {
                            "w_lat": 0.25,
                            "w_succ": 0.30,
                            "w_conn": 0.15,
                            "w_to": 0.20,
                            "w_ip": 0.10,
                        }
                    }
                }
            }
        }
    },
)
async def put_config(
    key: str,
    body: ConfigPutRequest,
    user: Annotated[User, Depends(require_roles("admin", "ops"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConfigItemResponse:
    item = await ConfigService(db).put(key, body.value, updated_by=user.id)
    if key.startswith("ip.rotation.") or key.startswith("routing."):
        enqueue_outbox(
            db,
            event_type="config.updated",
            topic="config",
            payload={"key": key, "version": item.version},
        )
        await db.commit()
        await db.refresh(item)
    return ConfigItemResponse.model_validate(item)
