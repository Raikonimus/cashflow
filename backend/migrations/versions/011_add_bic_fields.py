"""add bic to partner_accounts and partner_bic_raw to journal_lines

Revision ID: 011
Revises: 010
Create Date: 2026-04-07

"""
# pyright: reportAttributeAccessIssue=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("partner_accounts") as batch_op:
        batch_op.add_column(sa.Column("bic", sa.String(length=11), nullable=True))

    with op.batch_alter_table("journal_lines") as batch_op:
        batch_op.add_column(sa.Column("partner_bic_raw", sa.String(length=11), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("journal_lines") as batch_op:
        batch_op.drop_column("partner_bic_raw")

    with op.batch_alter_table("partner_accounts") as batch_op:
        batch_op.drop_column("bic")
