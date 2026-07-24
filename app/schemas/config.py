import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConfigItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: dict[str, Any]
    version: int
    updated_by: uuid.UUID | None = None
    updated_at: datetime | None = None


class ConfigPutRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "value": {
                        "w_lat": 0.25,
                        "w_succ": 0.30,
                        "w_conn": 0.15,
                        "w_to": 0.20,
                        "w_ip": 0.10,
                    }
                }
            ]
        }
    )

    value: dict[str, Any] = Field(default_factory=dict)
