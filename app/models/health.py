import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.db.base import Base


class HealthSnapshot(Base):
    __tablename__ = "health_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=False, index=True
    )
    latency_ms: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    success_rate: Mapped[float | None] = mapped_column(Numeric(8, 6), nullable=True)
    timeout_rate: Mapped[float | None] = mapped_column(Numeric(8, 6), nullable=True)
    connectivity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ip_health: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    score: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="healthy")
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FailoverEvent(Base):
    __tablename__ = "failover_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id"), nullable=True, index=True
    )
    from_broker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=False
    )
    to_broker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
