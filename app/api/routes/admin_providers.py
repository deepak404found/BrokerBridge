import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import (
    AUTH_ERRORS,
    NOT_FOUND,
    PROVIDER_GET_SUCCESS,
    PROVIDER_LIST_SUCCESS,
    PROVIDER_PUT_SUCCESS,
    UNPROCESSABLE,
)
from app.auth.deps import require_roles
from app.config.settings import Settings, get_settings
from app.core.crypto import encrypt_secret
from app.core.errors import AppError
from app.db.session import get_db
from app.models.provider_config import (
    ProviderConfig,
    ProviderKind,
    ProviderScope,
    ProviderStatus,
)
from app.models.user import User
from app.providers.manager import get_provider_manager
from app.schemas.providers import ProviderActivateRequest, ProviderConfigResponse

# Router-level 401/403 so every protected admin route documents auth errors in OpenAPI
# (OAuth2PasswordBearer uses auto_error=False so FastAPI does not auto-declare 401).
router = APIRouter(
    prefix="/api/v1/admin/providers",
    tags=["admin"],
    responses=AUTH_ERRORS,
)

_SECRET_KEYS = {"api_key", "password", "token", "secret"}


def _mask_config(config: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in config.items():
        if k.lower() in _SECRET_KEYS or "secret" in k.lower() or "key" in k.lower():
            out[k] = "***"
        else:
            out[k] = v
    return out


def _split_config(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    secrets: dict[str, Any] = {}
    public: dict[str, Any] = {}
    for k, v in config.items():
        if k.lower() in _SECRET_KEYS or "secret" in k.lower() or k.lower().endswith("_key"):
            secrets[k] = v
        else:
            public[k] = v
    return secrets, public


@router.get(
    "",
    response_model=list[ProviderConfigResponse],
    summary="List active provider configs",
    responses=PROVIDER_LIST_SUCCESS,
)
async def list_providers(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
) -> list[ProviderConfigResponse]:
    result = await db.execute(
        select(ProviderConfig).where(ProviderConfig.status == ProviderStatus.active)
    )
    rows = result.scalars().all()
    return [
        ProviderConfigResponse(
            kind=r.kind.value,
            provider_type=r.provider_type,
            version=r.version,
            status=r.status.value,
            config=_mask_config(dict(r.config_non_secret or {})),
            activated_at=r.activated_at,
        )
        for r in rows
    ]


@router.get(
    "/{kind}",
    response_model=ProviderConfigResponse,
    summary="Get active provider by kind",
    responses={**PROVIDER_GET_SUCCESS, **NOT_FOUND},
)
async def get_provider(
    kind: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
) -> ProviderConfigResponse:
    try:
        pkind = ProviderKind(kind)
    except ValueError as exc:
        raise AppError("NOT_FOUND", f"Unknown provider kind: {kind}", status_code=404) from exc
    result = await db.execute(
        select(ProviderConfig).where(
            ProviderConfig.kind == pkind,
            ProviderConfig.status == ProviderStatus.active,
        )
    )
    rows = [r for r in result.scalars().all() if r.client_id is None]
    if not rows:
        raise AppError("NOT_FOUND", "No active provider config", status_code=404)
    r = rows[0]
    return ProviderConfigResponse(
        kind=r.kind.value,
        provider_type=r.provider_type,
        version=r.version,
        status=r.status.value,
        config=_mask_config(dict(r.config_non_secret or {})),
        activated_at=r.activated_at,
    )


@router.put(
    "/{kind}",
    response_model=ProviderConfigResponse,
    summary="Activate or stage a provider config",
    responses={**PROVIDER_PUT_SUCCESS, **NOT_FOUND, **UNPROCESSABLE},
)
async def activate_provider(
    kind: str,
    body: ProviderActivateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProviderConfigResponse:
    try:
        pkind = ProviderKind(kind)
    except ValueError as exc:
        raise AppError("NOT_FOUND", f"Unknown provider kind: {kind}", status_code=404) from exc

    manager = get_provider_manager()
    validated = False
    if body.validate_first:
        if body.provider_type == "mock":
            if pkind == ProviderKind.infrastructure:
                probe = await (await manager.get_infrastructure_provider(db)).probe()
            else:
                probe = await (await manager.get_broker_provider(db)).probe()
            if not probe.get("ok"):
                raise AppError(
                    "PROVIDER_VALIDATION_FAILED",
                    "Provider probe failed",
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    details=probe,
                )
            validated = True
        elif body.provider_type == "vultr" and not body.config.get("api_key"):
            raise AppError(
                "PROVIDER_VALIDATION_FAILED",
                "Vultr api_key required",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        else:
            # Unknown real providers: accept mock-only in W1
            if body.provider_type != "mock":
                raise AppError(
                    "PROVIDER_VALIDATION_FAILED",
                    f"Provider type '{body.provider_type}' not supported in W1 (use mock)",
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                )
            validated = True

    secrets, public = _split_config(body.config)
    encrypted = encrypt_secret(json.dumps(secrets), settings) if secrets else None

    result = await db.execute(
        select(ProviderConfig).where(ProviderConfig.kind == pkind).order_by(ProviderConfig.version.desc())
    )
    latest = result.scalars().first()
    next_version = (latest.version + 1) if latest else 1

    await db.execute(
        update(ProviderConfig)
        .where(
            ProviderConfig.kind == pkind,
            ProviderConfig.status == ProviderStatus.active,
        )
        .values(status=ProviderStatus.retired)
    )

    row = ProviderConfig(
        kind=pkind,
        provider_type=body.provider_type,
        scope_type=ProviderScope.global_,
        client_id=body.client_id,
        status=ProviderStatus.active if body.activate else ProviderStatus.pending,
        version=next_version,
        config_encrypted=encrypted,
        config_non_secret=public,
        last_validation_status="ok" if validated else None,
        last_validation_at=datetime.now(UTC) if validated else None,
        activated_at=datetime.now(UTC) if body.activate else None,
        created_by=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    manager.invalidate(kind)

    return ProviderConfigResponse(
        kind=row.kind.value,
        provider_type=row.provider_type,
        version=row.version,
        status=row.status.value,
        config=_mask_config({**public, **{k: "***" for k in secrets}}),
        validated=validated,
        activated_at=row.activated_at,
    )
