"""drop partner patterns

Revision ID: 018_drop_partner_patterns
Revises: 017_add_service_assignment_fields
Create Date: 2026-04-13 21:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "018_drop_partner_patterns"
down_revision = "017_add_service_assignment_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_partner_patterns_partner_id", table_name="partner_patterns")
    op.drop_table("partner_patterns")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for dropping partner patterns")