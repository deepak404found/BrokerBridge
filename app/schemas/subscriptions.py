from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "client_id": "22222222-2222-4222-8222-222222222222",
                "starts_at": "2026-01-01T00:00:00Z",
                "ends_at": "2026-12-31T23:59:59Z",
                "teardown_mode": "SUSPEND",
            }
        }
    )

    client_id: UUID
    starts_at: datetime
    ends_at: datetime
    teardown_mode: str | None = Field(default=None, examples=["SUSPEND", "DESTROY"])


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID
    status: str
    starts_at: datetime
    ends_at: datetime
    teardown_mode: str
    teardown_completed_at: datetime | None = None
    created_at: datetime | None = None


class EnforceExpiryResponse(BaseModel):
    expired: int
    instances_torn_down: int
