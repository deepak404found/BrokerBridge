from typing import Any

from pydantic import BaseModel, Field


class DashboardResponse(BaseModel):
    health: dict[str, Any]
    sessions: dict[str, Any]
    static_ips: dict[str, Any]
    failovers: dict[str, Any]
    rate_limits: dict[str, Any]
    engine: dict[str, Any]
    orders_total: int = 0
    broker_health: dict[str, Any] = Field(default_factory=dict)
    events: dict[str, Any] = Field(default_factory=dict)
    simulator: dict[str, Any] = Field(default_factory=dict)
