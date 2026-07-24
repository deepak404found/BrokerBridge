from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RotateIpRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"force": False},
            "examples": [{"force": False}, {"force": True}],
        }
    )

    force: bool = Field(default=False, description="Force cutover if drain times out")


class RotateIpResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "broker_account_id": "11111111-1111-4111-8111-111111111111",
                "old_ip_id": "44444444-4444-4444-8444-444444444444",
                "new_ip_id": "55555555-5555-4555-8555-555555555555",
                "old_ip": "198.51.100.10",
                "new_ip": "198.51.100.22",
                "old_assignment_id": "66666666-6666-4666-8666-666666666666",
                "new_assignment_id": "77777777-7777-4777-8777-777777777777",
                "force": False,
                "drained": True,
                "whitelist_ok": True,
                "status": "rotated",
            }
        }
    )

    broker_account_id: UUID
    old_ip_id: UUID
    new_ip_id: UUID
    old_ip: str
    new_ip: str
    old_assignment_id: UUID
    new_assignment_id: UUID
    force: bool
    drained: bool
    whitelist_ok: bool
    status: str


class OutboxEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    topic: str
    payload: dict[str, Any]
    status: str
    error: str | None = None
    correlation_id: str | None = None
    created_at: datetime
    sent_at: datetime | None = None


class OutboxDrainResponse(BaseModel):
    sent: int
    error: int
    pending: int
