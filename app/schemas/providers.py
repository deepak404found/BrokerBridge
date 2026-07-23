from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProviderActivateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "provider_type": "mock",
                    "scope": "global",
                    "client_id": None,
                    "validate_first": True,
                    "activate": True,
                    "config": {"region": "ewr", "api_key": "vultr-secret-key"},
                }
            ]
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
            "examples": [
                {
                    "kind": "infrastructure",
                    "provider_type": "mock",
                    "version": 1,
                    "status": "active",
                    "config": {"region": "ewr", "api_key": "***"},
                    "validated": True,
                    "activated_at": "2026-07-23T12:00:00Z",
                }
            ]
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
