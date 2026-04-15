"""cleanup review items for zero-amount journal lines

Revision ID: 019_cleanup_zero_amount_reviews
Revises: 018_drop_partner_patterns
Create Date: 2026-04-13 22:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "019_cleanup_zero_amount_reviews"
down_revision = "018_drop_partner_patterns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM review_items
        WHERE journal_line_id IN (
            SELECT id FROM journal_lines WHERE amount = 0
        )
    """)


def downgrade() -> None:
    # Deleted review items cannot be restored.
    pass
