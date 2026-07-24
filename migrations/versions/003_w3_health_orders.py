"""Wave 3 tables: orders, attempts, health, failovers.

Revision ID: 003_w3
Revises: 002_w2
Create Date: 2026-07-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_w3"
down_revision: Union[str, Sequence[str], None] = "002_w2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("client_order_id", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("time_in_force", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("broker_account_id", sa.Uuid(), nullable=True),
        sa.Column("static_ip_id", sa.Uuid(), nullable=True),
        sa.Column("preferred_broker_id", sa.Uuid(), nullable=True),
        sa.Column("region_preference", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["broker_account_id"], ["broker_accounts.id"]),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["static_ip_id"], ["static_ips.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "client_order_id", name="uq_orders_client_client_order_id"),
    )
    op.create_index(op.f("ix_orders_client_id"), "orders", ["client_id"])
    op.create_index(op.f("ix_orders_status"), "orders", ["status"])
    op.create_index(op.f("ix_orders_broker_account_id"), "orders", ["broker_account_id"])

    op.create_table(
        "order_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("static_ip_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["broker_account_id"], ["broker_accounts.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["static_ip_id"], ["static_ips.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_attempts_order_id"), "order_attempts", ["order_id"])
    op.create_index(op.f("ix_order_attempts_broker_account_id"), "order_attempts", ["broker_account_id"])
    op.create_index(op.f("ix_order_attempts_status"), "order_attempts", ["status"])

    op.create_table(
        "health_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("latency_ms", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("success_rate", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("timeout_rate", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("connectivity", sa.Boolean(), nullable=False),
        sa.Column("ip_health", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("score", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["broker_account_id"], ["broker_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_health_snapshots_broker_account_id"), "health_snapshots", ["broker_account_id"])

    op.create_table(
        "failover_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("from_broker_id", sa.Uuid(), nullable=False),
        sa.Column("to_broker_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["from_broker_id"], ["broker_accounts.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["to_broker_id"], ["broker_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_failover_events_order_id"), "failover_events", ["order_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_failover_events_order_id"), table_name="failover_events")
    op.drop_table("failover_events")
    op.drop_index(op.f("ix_health_snapshots_broker_account_id"), table_name="health_snapshots")
    op.drop_table("health_snapshots")
    op.drop_index(op.f("ix_order_attempts_status"), table_name="order_attempts")
    op.drop_index(op.f("ix_order_attempts_broker_account_id"), table_name="order_attempts")
    op.drop_index(op.f("ix_order_attempts_order_id"), table_name="order_attempts")
    op.drop_table("order_attempts")
    op.drop_index(op.f("ix_orders_broker_account_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_client_id"), table_name="orders")
    op.drop_table("orders")
