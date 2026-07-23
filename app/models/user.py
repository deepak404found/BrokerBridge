import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class UserRole(str, enum.Enum):
    client = "client"
    admin = "admin"
    ops = "ops"
    readonly = "readonly"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="client")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[Client | None] = relationship(back_populates="users")
