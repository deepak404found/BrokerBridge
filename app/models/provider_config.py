import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.db.base import Base


class ProviderKind(str, enum.Enum):
    infrastructure = "infrastructure"
    broker_default = "broker_default"
    event = "event"
    cache = "cache"
    lock = "lock"
    session = "session"


class ProviderScope(str, enum.Enum):
    global_ = "global"
    client = "client"


class ProviderStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    retired = "retired"
    failed_validation = "failed_validation"


class ProviderConfig(Base):
    __tablename__ = "provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[ProviderKind] = mapped_column(Enum(ProviderKind, name="provider_kind"), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[ProviderScope] = mapped_column(
        Enum(ProviderScope, name="provider_scope"), nullable=False, default=ProviderScope.global_
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[ProviderStatus] = mapped_column(
        Enum(ProviderStatus, name="provider_status"), nullable=False, default=ProviderStatus.pending
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_non_secret: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=dict)
    last_validation_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_validation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
