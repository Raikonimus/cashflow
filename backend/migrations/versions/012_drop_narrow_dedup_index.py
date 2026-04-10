"""drop uq_journal_lines_dedup — duplicate detection moved to Python (all fields)

Der alte Index deckte nur (account_id, valuta_date, booking_date, amount,
partner_iban_raw, partner_name_raw) ab und blockierte legitime Mehrfachbuchungen
(gleicher Betrag, gleicher Tag, verschiedener Text/Partner). Die vollständige
Duplikaterkennung erfolgt jetzt in Python mit allen Feldern inkl. unmapped_data.

Revision ID: 012
Revises: 011
Create Date: 2026-04-08

"""
# pyright: reportAttributeAccessIssue=false
from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_journal_lines_dedup", table_name="journal_lines")


def downgrade() -> None:
    op.create_index(
        "uq_journal_lines_dedup",
        "journal_lines",
        ["account_id", "valuta_date", "booking_date", "amount"],
        unique=True,
    )
