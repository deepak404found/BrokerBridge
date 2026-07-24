from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.openapi import AUTH_ERRORS, NOT_FOUND, UNPROCESSABLE, success_response
from app.auth.deps import require_roles
from app.config.settings import Settings, get_settings
from app.db.session import get_db
from app.ip_manager.service import IpManagerService
from app.models.user import User
from app.providers.manager import get_provider_manager
from app.schemas.infrastructure import (
    AllocateIpRequest,
    AssignIpRequest,
    AssignmentResponse,
    AttachIpRequest,
    InstanceCreateRequest,
    InstanceResponse,
    StaticIpResponse,
    WhitelistFindingResponse,
    WhitelistSyncResponse,
)
from app.whitelist.service import WhitelistService

router = APIRouter(
    prefix="/api/v1/infrastructure",
    tags=["infrastructure"],
    responses=AUTH_ERRORS,
)

_IP_EXAMPLE = {
    "id": "44444444-4444-4444-8444-444444444444",
    "provider": "mock",
    "external_id": "mock-ip-abc123",
    "ip_address": "198.51.100.42",
    "region": "ewr",
    "status": "allocated",
    "instance_id": None,
    "health_score": 100,
    "created_at": "2026-07-24T10:00:00Z",
}

_ASSIGN_EXAMPLE = {
    "id": "55555555-5555-4555-8555-555555555555",
    "client_id": "22222222-2222-4222-8222-222222222222",
    "broker_account_id": "11111111-1111-4111-8111-111111111111",
    "broker_display_name": "Mock Alpha Broker",
    "static_ip_id": "44444444-4444-4444-8444-444444444444",
    "ip_address": "198.51.100.42",
    "ip_status": "attached",
    "region": "ewr",
    "status": "active",
    "assigned_at": "2026-07-24T10:05:00Z",
    "released_at": None,
}

_WL_EXAMPLE = {
    "snapshot_id": "66666666-6666-4666-8666-666666666666",
    "broker_account_id": "11111111-1111-4111-8111-111111111111",
    "raw_format": "json",
    "normalized": {"ips": ["198.51.100.10", "198.51.100.11"], "count": 2},
    "findings": [
        {
            "id": "77777777-7777-4777-8777-777777777777",
            "broker_account_id": "11111111-1111-4111-8111-111111111111",
            "ip_address": "198.51.100.42",
            "finding_type": "missing",
            "details": {"expected": True, "on_broker_whitelist": False},
            "detected_at": "2026-07-24T10:10:00Z",
            "resolved_at": None,
        }
    ],
    "fetched_at": "2026-07-24T10:10:00Z",
}


def _ip_svc(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IpManagerService:
    return IpManagerService(db, settings, get_provider_manager())


def _wl_svc(
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WhitelistService:
    return WhitelistService(db, settings, get_provider_manager())


@router.post(
    "/instances",
    response_model=InstanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision mock instance",
)
async def create_instance(
    body: InstanceCreateRequest,
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[IpManagerService, Depends(_ip_svc)],
) -> InstanceResponse:
    row = await svc.create_instance(client_id=body.client_id, region=body.region, label=body.label)
    return InstanceResponse.model_validate(row)


@router.get(
    "/instances",
    response_model=list[InstanceResponse],
    summary="List instances",
)
async def list_instances(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    svc: Annotated[IpManagerService, Depends(_ip_svc)],
) -> list[InstanceResponse]:
    return [InstanceResponse.model_validate(r) for r in await svc.list_instances()]


@router.delete(
    "/instances/{instance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Destroy instance",
    responses=NOT_FOUND,
)
async def destroy_instance(
    instance_id: UUID,
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[IpManagerService, Depends(_ip_svc)],
) -> Response:
    await svc.destroy_instance(instance_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/ips",
    response_model=StaticIpResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Allocate static IP",
    responses={201: success_response("IP allocated", example=_IP_EXAMPLE)},
)
async def allocate_ip(
    body: AllocateIpRequest,
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[IpManagerService, Depends(_ip_svc)],
) -> StaticIpResponse:
    return StaticIpResponse.model_validate(await svc.allocate_ip(region=body.region))


@router.get(
    "/ips",
    response_model=list[StaticIpResponse],
    summary="List static IPs",
    responses={200: success_response("IP list", example=[_IP_EXAMPLE])},
)
async def list_ips(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    svc: Annotated[IpManagerService, Depends(_ip_svc)],
) -> list[StaticIpResponse]:
    return [StaticIpResponse.model_validate(r) for r in await svc.list_ips()]


@router.post(
    "/ips/{ip_id}/assign",
    response_model=AssignmentResponse,
    summary="Assign IP to broker (BR-G04 enforced)",
    responses={
        200: success_response("Assigned", example=_ASSIGN_EXAMPLE),
        **NOT_FOUND,
        **UNPROCESSABLE,
    },
)
async def assign_ip(
    ip_id: UUID,
    body: AssignIpRequest,
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[IpManagerService, Depends(_ip_svc)],
) -> AssignmentResponse:
    assignment = await svc.assign(
        ip_id=ip_id,
        broker_account_id=body.broker_account_id,
        client_id=body.client_id,
    )
    rows = await svc.list_assignments()
    match = next(r for r in rows if r["id"] == assignment.id)
    return AssignmentResponse(**match)


@router.post(
    "/ips/{ip_id}/attach",
    response_model=StaticIpResponse,
    summary="Attach IP to instance",
    responses={200: success_response("Attached", example={**_IP_EXAMPLE, "status": "attached"}), **NOT_FOUND},
)
async def attach_ip(
    ip_id: UUID,
    body: AttachIpRequest,
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[IpManagerService, Depends(_ip_svc)],
) -> StaticIpResponse:
    return StaticIpResponse.model_validate(await svc.attach(ip_id, instance_id=body.instance_id))


@router.post(
    "/ips/{ip_id}/detach",
    response_model=StaticIpResponse,
    summary="Detach IP from instance",
    responses={200: success_response("Detached", example={**_IP_EXAMPLE, "status": "detached"}), **NOT_FOUND},
)
async def detach_ip(
    ip_id: UUID,
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[IpManagerService, Depends(_ip_svc)],
) -> StaticIpResponse:
    return StaticIpResponse.model_validate(await svc.detach(ip_id))


@router.delete(
    "/ips/{ip_id}",
    response_model=StaticIpResponse,
    summary="Release static IP",
    responses={200: success_response("Released", example={**_IP_EXAMPLE, "status": "released"}), **NOT_FOUND},
)
async def release_ip(
    ip_id: UUID,
    _: Annotated[User, Depends(require_roles("admin"))],
    svc: Annotated[IpManagerService, Depends(_ip_svc)],
) -> StaticIpResponse:
    return StaticIpResponse.model_validate(await svc.release(ip_id))


@router.get(
    "/assignments",
    response_model=list[AssignmentResponse],
    summary="Client/broker/IP assignment map",
    responses={200: success_response("Assignments", example=[_ASSIGN_EXAMPLE])},
)
async def list_assignments(
    _: Annotated[User, Depends(require_roles("admin", "ops", "readonly"))],
    svc: Annotated[IpManagerService, Depends(_ip_svc)],
) -> list[AssignmentResponse]:
    return [AssignmentResponse(**r) for r in await svc.list_assignments()]


@router.post(
    "/brokers/{broker_id}/whitelist/sync",
    response_model=WhitelistSyncResponse,
    summary="Sync broker whitelist now",
    responses={200: success_response("Whitelist synced", example=_WL_EXAMPLE), **NOT_FOUND},
)
async def sync_whitelist(
    broker_id: UUID,
    _: Annotated[User, Depends(require_roles("admin", "ops"))],
    svc: Annotated[WhitelistService, Depends(_wl_svc)],
) -> WhitelistSyncResponse:
    result = await svc.sync(broker_id)
    snapshot = result["snapshot"]
    return WhitelistSyncResponse(
        snapshot_id=snapshot.id,
        broker_account_id=broker_id,
        raw_format=snapshot.raw_format,
        normalized=result["normalized"],
        findings=[WhitelistFindingResponse.model_validate(f) for f in result["findings"]],
        fetched_at=snapshot.fetched_at,
    )
