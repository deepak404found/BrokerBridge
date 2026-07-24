import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderPlaceRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "client_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "client_order_id": "c-10001",
                    "symbol": "AAPL",
                    "quantity": 10,
                    "order_type": "MARKET",
                    "time_in_force": "DAY",
                    "preferred_broker_id": None,
                    "region_preference": "ewr",
                }
            ]
        }
    )

    client_id: uuid.UUID = Field(description="Demo/admin client id (seed Demo Lab Client)")
    client_order_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=64)
    quantity: Decimal = Field(gt=0)
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    time_in_force: Literal["DAY", "GTC", "IOC"] = "DAY"
    preferred_broker_id: uuid.UUID | None = None
    region_preference: str | None = None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    client_order_id: str
    side: str
    symbol: str
    quantity: Decimal
    order_type: str
    time_in_force: str
    status: str
    broker_account_id: uuid.UUID | None = None
    static_ip_id: uuid.UUID | None = None
    preferred_broker_id: uuid.UUID | None = None
    region_preference: str | None = None
    broker_order_id: str | None = None
    error_code: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    limit: int
    offset: int
