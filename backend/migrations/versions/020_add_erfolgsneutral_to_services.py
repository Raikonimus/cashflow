"""add erfolgsneutral to services

Revision ID: 020
Revises: 019
Create Date: 2026-04-15

"""
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context
from alembic.operations import Operations

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.add_column(
        "services",
        sa.Column("erfolgsneutral", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.drop_column("services", "erfolgsneutral")
