"""add forecast_snapshots

Revision ID: 028
Revises: 027
Create Date: 2026-09-09 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mandant_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("scenario", sa.String(10), nullable=False, server_default="expected"),
        sa.Column("as_of", sa.String(10), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("start_balance", sa.Numeric(15, 2), nullable=False),
        sa.Column("months", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forecast_snapshots_mandant_id", "forecast_snapshots", ["mandant_id"])


def downgrade() -> None:
    op.drop_table("forecast_snapshots")
