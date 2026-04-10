"""add account_excluded_identifiers

Revision ID: 013
Revises: 012
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_excluded_identifiers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("identifier_type", sa.String(20), nullable=False),  # "iban" | "account_number"
        sa.Column("value", sa.String(50), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("account_id", "identifier_type", "value", name="uq_excluded_identifier"),
    )


def downgrade() -> None:
    op.drop_table("account_excluded_identifiers")
