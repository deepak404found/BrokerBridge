from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InstanceCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "client_id": "22222222-2222-4222-8222-222222222222",
                "region": "ewr",
                "label": "Lab gateway ewr",
            }
        }
    )

    client_id: UUID
    region: str = Field(default="ewr", examples=["ewr"])
    label: str | None = Field(default=None, examples=["Lab gateway ewr"])


class InstanceResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "33333333-3333-4333-8333-333333333333",
                "client_id": "22222222-2222-4222-8222-222222222222",
                "provider": "mock",
                "external_id": "mock-inst-abc123",
                "display_name": "Lab Instance ewr-abc123",
                "region": "ewr",
                "status": "running",
                "auto_renew": True,
                "created_at": "2026-07-24T10:00:00Z",
            }
        },
    )

    id: UUID
    client_id: UUID
    provider: str
    external_id: str
    display_name: str
    region: str
    status: str
    auto_renew: bool
    created_at: datetime | None = None


class AllocateIpRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"region": "ewr"}})

    region: str = Field(default="ewr", examples=["ewr"])


class StaticIpResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
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
        },
    )

    id: UUID
    provider: str
    external_id: str
    ip_address: str
    region: str
    status: str
    instance_id: UUID | None = None
    health_score: int | None = None
    created_at: datetime | None = None


class AssignIpRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "broker_account_id": "11111111-1111-4111-8111-111111111111",
                "client_id": "22222222-2222-4222-8222-222222222222",
            }
        }
    )

    broker_account_id: UUID
    client_id: UUID | None = None


class AttachIpRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"instance_id": "33333333-3333-4333-8333-333333333333"}
        }
    )

    instance_id: UUID


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
        }
    )

    id: UUID
    client_id: UUID
    broker_account_id: UUID
    broker_display_name: str | None = None
    static_ip_id: UUID
    ip_address: str
    ip_status: str
    region: str
    status: str
    assigned_at: datetime | None = None
    released_at: datetime | None = None


class WhitelistFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    broker_account_id: UUID
    ip_address: str
    finding_type: str
    details: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime | None = None
    resolved_at: datetime | None = None


class WhitelistSyncResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
        }
    )

    snapshot_id: UUID
    broker_account_id: UUID
    raw_format: str
    normalized: dict[str, Any]
    findings: list[WhitelistFindingResponse]
    fetched_at: datetime | None = None
