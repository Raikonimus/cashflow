"""add manual_assignment to partners

Revision ID: 024
Revises: 023_add_service_amount_consistency_ok_to_journal_lines
Create Date: 2026-04-20 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "024"
down_revision = "023_add_service_amount_consistency_ok_to_journal_lines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("partners") as batch_op:
        batch_op.add_column(
            sa.Column(
                "manual_assignment",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("partners") as batch_op:
        batch_op.drop_column("manual_assignment")
