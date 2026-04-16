"""add internal_only to service_matchers

Revision ID: 021
Revises: 020
Create Date: 2026-04-15

"""
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context
from alembic.operations import Operations

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    migration_context = getattr(context, "get_context")()
    operations = Operations(migration_context)
    bind = migration_context.bind
    inspector = sa.inspect(bind)
    matcher_columns = {column["name"] for column in inspector.get_columns("service_matchers")}
    if "internal_only" not in matcher_columns:
        operations.add_column(
            "service_matchers",
            sa.Column("internal_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    migration_context = getattr(context, "get_context")()
    operations = Operations(migration_context)
    bind = migration_context.bind
    inspector = sa.inspect(bind)
    matcher_columns = {column["name"] for column in inspector.get_columns("service_matchers")}
    if "internal_only" in matcher_columns:
        operations.drop_column("service_matchers", "internal_only")
