"""Wave 6 tables: subscriptions + mock_infra_resources.

Revision ID: 005_w6
Revises: 004_w4
Create Date: 2026-07-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_w6"
down_revision: Union[str, Sequence[str], None] = "004_w4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("teardown_mode", sa.String(length=32), nullable=False),
        sa.Column("teardown_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subscriptions_client_id"), "subscriptions", ["client_id"])
    op.create_index(op.f("ix_subscriptions_status"), "subscriptions", ["status"])
    op.create_index(op.f("ix_subscriptions_ends_at"), "subscriptions", ["ends_at"])

    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "mock_infra_resources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("attached_instance_id", sa.String(length=128), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index(op.f("ix_mock_infra_resources_external_id"), "mock_infra_resources", ["external_id"])
    op.create_index(op.f("ix_mock_infra_resources_kind"), "mock_infra_resources", ["kind"])


def downgrade() -> None:
    op.drop_index(op.f("ix_mock_infra_resources_kind"), table_name="mock_infra_resources")
    op.drop_index(op.f("ix_mock_infra_resources_external_id"), table_name="mock_infra_resources")
    op.drop_table("mock_infra_resources")
    op.drop_index(op.f("ix_subscriptions_ends_at"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_status"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_client_id"), table_name="subscriptions")
    op.drop_table("subscriptions")
