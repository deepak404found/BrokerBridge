from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class BrokerCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "client_id": "22222222-2222-4222-8222-222222222222",
                "provider_type": "mock",
                "display_name": "Mock Gamma Broker",
                "priority": 30,
                "enabled": True,
                "allowed_regions": ["ewr"],
                "credentials": {"api_key": "mock-key", "api_secret": "mock-secret"},
                "rate_limit_rps": 40,
            }
        }
    )

    client_id: UUID = Field(examples=["22222222-2222-4222-8222-222222222222"])
    provider_type: str = Field(default="mock", examples=["mock"])
    display_name: str = Field(examples=["Mock Gamma Broker"])
    priority: int = Field(default=100, examples=[30])
    enabled: bool = Field(default=True, examples=[True])
    allowed_regions: list[str] = Field(default_factory=lambda: ["ewr"], examples=[["ewr"]])
    credentials: dict[str, Any] = Field(
        examples=[{"api_key": "mock-key", "api_secret": "mock-secret"}]
    )
    rate_limit_rps: Decimal | None = Field(default=None, examples=[40])


class BrokerPatchRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"enabled": False, "priority": 5}}
    )

    enabled: bool | None = Field(default=None, examples=[False])
    priority: int | None = Field(default=None, examples=[5])
    display_name: str | None = Field(default=None, examples=["Renamed Broker"])
    rate_limit_rps: Decimal | None = Field(default=None, examples=[20])
    allowed_regions: list[str] | None = Field(default=None, examples=[["ewr", "lax"]])


class BrokerResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={"example": _BROKER_EXAMPLE},
    )

    id: UUID
    client_id: UUID
    provider_type: str
    display_name: str
    priority: int
    enabled: bool
    allowed_regions: list[Any] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    rate_limit_rps: Decimal | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SessionStatusResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "broker_account_id": "11111111-1111-4111-8111-111111111111",
                "broker_display_name": "Mock Alpha Broker",
                "status": "valid",
                "expires_at": "2026-07-24T11:00:00Z",
                "updated_at": "2026-07-24T10:00:00Z",
                "has_tokens": True,
            }
        }
    )

    broker_account_id: UUID
    broker_display_name: str | None = None
    status: str
    expires_at: datetime | None = None
    updated_at: datetime | None = None
    has_tokens: bool = False
