"""add service amount consistency ok flag to journal lines

Revision ID: 023_add_service_amount_consistency_ok_to_journal_lines
Revises: 022_add_service_groups
Create Date: 2026-04-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "023_add_service_amount_consistency_ok_to_journal_lines"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("journal_lines") as batch_op:
        batch_op.add_column(
            sa.Column(
                "service_amount_consistency_ok",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("journal_lines") as batch_op:
        batch_op.drop_column("service_amount_consistency_ok")