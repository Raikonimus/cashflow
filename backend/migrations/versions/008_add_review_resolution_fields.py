"""add resolved_by and resolved_at to review_items

Revision ID: 008
Revises: 007
Create Date: 2026-04-07

"""
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context
from alembic.operations import Operations

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.add_column(
        "review_items",
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
    )
    operations.add_column(
        "review_items",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.drop_column("review_items", "resolved_at")
    operations.drop_column("review_items", "resolved_by")
