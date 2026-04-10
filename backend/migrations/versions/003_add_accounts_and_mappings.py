"""extend mandants, add accounts and column_mapping_configs

Revision ID: 003
Revises: 002
Create Date: 2026-04-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # mandants – add updated_at (was missing in stub)
    # ------------------------------------------------------------------
    op.add_column(
        "mandants",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ------------------------------------------------------------------
    # accounts
    # ------------------------------------------------------------------
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("iban", sa.String(34), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
        sa.UniqueConstraint("iban", name="uq_accounts_iban"),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandants.id"], name="fk_accounts_mandant", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_accounts_mandant_id", "accounts", ["mandant_id"])

    # ------------------------------------------------------------------
    # column_mapping_configs
    # ------------------------------------------------------------------
    op.create_table(
        "column_mapping_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("valuta_date_col", sa.String(100), nullable=False),
        sa.Column("booking_date_col", sa.String(100), nullable=False),
        sa.Column("amount_col", sa.String(100), nullable=False),
        sa.Column("partner_iban_col", sa.String(100), nullable=True),
        sa.Column("partner_name_col", sa.String(100), nullable=True),
        sa.Column("description_col", sa.String(100), nullable=True),
        sa.Column("decimal_separator", sa.String(1), nullable=False, server_default=","),
        sa.Column("date_format", sa.String(50), nullable=False, server_default="%d.%m.%Y"),
        sa.Column("encoding", sa.String(20), nullable=False, server_default="utf-8"),
        sa.Column("delimiter", sa.String(5), nullable=False, server_default=";"),
        sa.Column("skip_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_column_mapping_configs"),
        sa.UniqueConstraint("account_id", name="uq_column_mapping_configs_account"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_column_mapping_configs_account", ondelete="CASCADE"
        ),
    )


def downgrade() -> None:
    op.drop_table("column_mapping_configs")
    op.drop_index("ix_accounts_mandant_id", table_name="accounts")
    op.drop_table("accounts")
    op.drop_column("mandants", "updated_at")
