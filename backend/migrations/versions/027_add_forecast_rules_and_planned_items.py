"""add service_forecast_rules and forecast_planned_items

Revision ID: 027
Revises: 026
Create Date: 2026-09-09 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_forecast_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mandant_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False, server_default="auto"),
        sa.Column("rule_type", sa.String(30), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("adjustment_pct", sa.Numeric(6, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("shift_months", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", name="uq_service_forecast_rules_service"),
    )
    op.create_index(
        "ix_service_forecast_rules_mandant_id", "service_forecast_rules", ["mandant_id"]
    )
    op.create_index(
        "ix_service_forecast_rules_service_id", "service_forecast_rules", ["service_id"]
    )

    op.create_table(
        "forecast_planned_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mandant_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_planned_items_mandant_id", "forecast_planned_items", ["mandant_id"]
    )
    op.create_index(
        "ix_forecast_planned_items_service_id", "forecast_planned_items", ["service_id"]
    )
    op.create_index("ix_forecast_planned_items_period", "forecast_planned_items", ["period"])


def downgrade() -> None:
    op.drop_table("forecast_planned_items")
    op.drop_table("service_forecast_rules")
