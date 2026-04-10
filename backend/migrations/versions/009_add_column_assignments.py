"""add column_assignments to column_mapping_configs

Revision ID: 009
Revises: 008
Create Date: 2026-04-07

"""
# pyright: reportAttributeAccessIssue=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("column_mapping_configs") as batch_op:
        batch_op.add_column(sa.Column("column_assignments", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("column_mapping_configs") as batch_op:
        batch_op.drop_column("column_assignments")
