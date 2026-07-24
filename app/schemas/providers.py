from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


_ACTIVATE_EXAMPLE = {
    "provider_type": "mock",
    "scope": "global",
    "client_id": None,
    "validate_first": True,
    "activate": True,
    "config": {"region": "ewr", "api_key": "vultr-secret-key"},
}

_PROVIDER_RESPONSE_EXAMPLE = {
    "kind": "infrastructure",
    "provider_type": "mock",
    "version": 1,
    "status": "active",
    "config": {"region": "ewr", "api_key": "***"},
    "validated": True,
    "activated_at": "2026-07-23T12:00:00Z",
}


class ProviderActivateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": _ACTIVATE_EXAMPLE,
            "examples": [_ACTIVATE_EXAMPLE],
        }
    )

    provider_type: str = Field(examples=["mock"])
    scope: str = Field(default="global", examples=["global"])
    client_id: UUID | None = None
    validate_first: bool = True
    activate: bool = True
    config: dict[str, Any] = Field(
        default_factory=dict,
        examples=[{"region": "ewr", "api_key": "vultr-secret-key"}],
    )


class ProviderConfigResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": _PROVIDER_RESPONSE_EXAMPLE,
            "examples": [_PROVIDER_RESPONSE_EXAMPLE],
        }
    )

    kind: str = Field(examples=["infrastructure"])
    provider_type: str = Field(examples=["mock"])
    version: int = Field(examples=[1])
    status: str = Field(examples=["active"])
    config: dict[str, Any] = Field(examples=[{"region": "ewr", "api_key": "***"}])
    validated: bool | None = Field(default=None, examples=[True])
    activated_at: datetime | None = Field(
        default=None,
        examples=["2026-07-23T12:00:00Z"],
    )
    # Runtime resolution (infrastructure only): may differ from config.mock_backend
    # when docker is configured but the Engine/socket is unavailable.
    effective_backend: str | None = Field(default=None, examples=["database"])
    degraded: bool = Field(default=False, examples=[False])
    degrade_message: str | None = Field(default=None)
