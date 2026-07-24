import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthBrokerResponse(BaseModel):
    broker_account_id: uuid.UUID
    broker_display_name: str
    enabled: bool
    latency_ms: float
    success_rate: float
    timeout_rate: float
    connectivity: bool
    ip_health: float
    score: float
    status: str
    measured_at: datetime | None = None
    breakdown: dict[str, Any] = Field(default_factory=dict)


class RateLimitSnapshotResponse(BaseModel):
    broker_account_id: uuid.UUID
    broker_display_name: str
    limit_rps: float
    used: float
    remaining: float
    pressure: float
    window_seconds: float


class FailoverEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID | None = None
    from_broker_id: uuid.UUID
    to_broker_id: uuid.UUID
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class OrdersEngineResponse(BaseModel):
    inflight: int
    max_inflight: int
    by_status: dict[str, int]
    execution_mode: str


class RoutingPreviewRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "client_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "preferred_broker_id": None,
                    "region_preference": "ewr",
                }
            ]
        }
    )

    client_id: uuid.UUID
    preferred_broker_id: uuid.UUID | None = None
    region_preference: str | None = None


class RoutingPreviewResponse(BaseModel):
    require_assigned_ip: bool
    primary: dict[str, Any] | None = None
    chain: list[dict[str, Any]] = Field(default_factory=list)
    excluded: list[dict[str, Any]] = Field(default_factory=list)
