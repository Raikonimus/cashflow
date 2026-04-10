"""add import_runs and journal_lines tables

Revision ID: 006
Revises: 005
Create Date: 2026-04-06

"""
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


json_type = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()), "postgresql"
)


def upgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    # ------------------------------------------------------------------
    # import_runs
    # ------------------------------------------------------------------
    operations.create_table(
        "import_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_details", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_import_runs"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_import_runs_account", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandants.id"], name="fk_import_runs_mandant", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_import_runs_user"
        ),
    )
    operations.create_index("ix_import_runs_account_id", "import_runs", ["account_id"])
    operations.create_index("ix_import_runs_mandant_id", "import_runs", ["mandant_id"])
    operations.create_index("ix_import_runs_created_at", "import_runs", ["created_at"])

    # ------------------------------------------------------------------
    # journal_lines
    # ------------------------------------------------------------------
    operations.create_table(
        "journal_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("valuta_date", sa.Date(), nullable=False),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("text", sa.String(1000), nullable=True),
        sa.Column("partner_name_raw", sa.String(500), nullable=True),
        sa.Column("partner_iban_raw", sa.String(34), nullable=True),
        sa.Column("unmapped_data", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_journal_lines"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_journal_lines_account", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["import_run_id"], ["import_runs.id"], name="fk_journal_lines_import_run"
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"], ["partners.id"], name="fk_journal_lines_partner", ondelete="SET NULL"
        ),
    )
    operations.create_index("ix_journal_lines_account_id", "journal_lines", ["account_id"])
    operations.create_index("ix_journal_lines_import_run_id", "journal_lines", ["import_run_id"])
    operations.create_index("ix_journal_lines_partner_id", "journal_lines", ["partner_id"])

    # Dubletten-Constraint (NULL-safe via COALESCE)
    operations.execute(
        "CREATE UNIQUE INDEX uq_journal_lines_dedup ON journal_lines ("
        "account_id, valuta_date, booking_date, amount, "
        "COALESCE(partner_iban_raw, ''), COALESCE(partner_name_raw, '')"
        ")"
    )


def downgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.drop_index("uq_journal_lines_dedup", table_name="journal_lines")
    operations.drop_index("ix_journal_lines_partner_id", table_name="journal_lines")
    operations.drop_index("ix_journal_lines_import_run_id", table_name="journal_lines")
    operations.drop_index("ix_journal_lines_account_id", table_name="journal_lines")
    operations.drop_table("journal_lines")

    operations.drop_index("ix_import_runs_created_at", table_name="import_runs")
    operations.drop_index("ix_import_runs_mandant_id", table_name="import_runs")
    operations.drop_index("ix_import_runs_account_id", table_name="import_runs")
    operations.drop_table("import_runs")
