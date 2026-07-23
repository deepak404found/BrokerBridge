"""Initial clients, users, provider_configs.

Revision ID: 001_initial
Revises:
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "role",
            sa.Enum("client", "admin", "ops", "readonly", name="user_role"),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("api_key_hash", sa.String(length=255), nullable=True),
        sa.Column("api_key_prefix", sa.String(length=16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "provider_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "infrastructure",
                "broker_default",
                "event",
                "cache",
                "lock",
                "session",
                name="provider_kind",
            ),
            nullable=False,
        ),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column(
            "scope_type",
            sa.Enum("global", "client", name="provider_scope"),
            nullable=False,
        ),
        sa.Column("client_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "active", "retired", "failed_validation", name="provider_status"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_encrypted", sa.Text(), nullable=True),
        sa.Column("config_non_secret", sa.JSON(), nullable=True),
        sa.Column("last_validation_status", sa.String(length=64), nullable=True),
        sa.Column("last_validation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("provider_configs")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_table("clients")
    sa.Enum(name="provider_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="provider_scope").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="provider_kind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
