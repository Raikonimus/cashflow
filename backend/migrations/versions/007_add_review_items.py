"""add review_items table

Revision ID: 007
Revises: 006
Create Date: 2026-04-07

"""
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context
from alembic.operations import Operations

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.create_table(
        "review_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mandant_id", sa.Uuid(), nullable=False),
        sa.Column("item_type", sa.String(50), nullable=False),
        sa.Column("journal_line_id", sa.Uuid(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["journal_line_id"], ["journal_lines.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("journal_line_id", name="uq_review_items_journal_line"),
    )
    operations.create_index("ix_review_items_mandant_id", "review_items", ["mandant_id"])
    operations.create_index("ix_review_items_status", "review_items", ["status"])


def downgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.drop_index("ix_review_items_status", "review_items")
    operations.drop_index("ix_review_items_mandant_id", "review_items")
    operations.drop_table("review_items")
