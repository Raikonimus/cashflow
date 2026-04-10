"""add partner_accounts table and blz/account fields to journal_lines

Revision ID: 010
Revises: 009
Create Date: 2026-04-07

"""
# pyright: reportAttributeAccessIssue=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "partner_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("blz", sa.String(length=20), nullable=True),
        sa.Column("account_number", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blz", "account_number", name="uq_partner_accounts_blz_account"),
    )
    op.create_index("ix_partner_accounts_partner_id", "partner_accounts", ["partner_id"])

    with op.batch_alter_table("journal_lines") as batch_op:
        batch_op.add_column(sa.Column("partner_account_raw", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("partner_blz_raw", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("journal_lines") as batch_op:
        batch_op.drop_column("partner_blz_raw")
        batch_op.drop_column("partner_account_raw")

    op.drop_index("ix_partner_accounts_partner_id", table_name="partner_accounts")
    op.drop_table("partner_accounts")
