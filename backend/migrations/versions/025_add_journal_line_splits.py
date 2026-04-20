"""add journal_line_splits and remove service fields from journal_lines

Revision ID: 025
Revises: 024
Create Date: 2026-04-20 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Neue Tabelle journal_line_splits anlegen
    op.create_table(
        "journal_line_splits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("journal_line_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("assignment_mode", sa.String(20), nullable=False),
        sa.Column("amount_consistency_ok", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["journal_line_id"], ["journal_lines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journal_line_splits_journal_line_id", "journal_line_splits", ["journal_line_id"])
    op.create_index("ix_journal_line_splits_service_id", "journal_line_splits", ["service_id"])

    # 2. Bestehende Zuordnungen migrieren:
    #    Jede journal_line mit service_id bekommt einen Split-Eintrag.
    #    amount_consistency_ok wird von journal_lines übernommen.
    op.execute("""
        INSERT INTO journal_line_splits
            (id, journal_line_id, service_id, amount, assignment_mode, amount_consistency_ok, created_at, updated_at)
        SELECT
            lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' ||
                substr(lower(hex(randomblob(2))),2) || '-' ||
                substr('89ab',abs(random()) % 4 + 1, 1) ||
                substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6))),
            id,
            service_id,
            amount,
            COALESCE(service_assignment_mode, 'auto'),
            CASE WHEN service_amount_consistency_ok = 1 THEN 1 ELSE 0 END,
            created_at,
            created_at
        FROM journal_lines
        WHERE service_id IS NOT NULL
    """)

    # 3. Alte Spalten aus journal_lines entfernen
    with op.batch_alter_table("journal_lines") as batch_op:
        batch_op.drop_index("ix_journal_lines_service_id")
        batch_op.drop_column("service_id")
        batch_op.drop_column("service_assignment_mode")
        batch_op.drop_column("service_amount_consistency_ok")


def downgrade() -> None:
    # 1. Spalten wiederherstellen
    with op.batch_alter_table("journal_lines") as batch_op:
        batch_op.add_column(sa.Column("service_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("service_assignment_mode", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("service_amount_consistency_ok", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    op.create_index("ix_journal_lines_service_id", "journal_lines", ["service_id"])

    # 2. Daten zurück migrieren (erster Split je Zeile)
    op.execute("""
        UPDATE journal_lines
        SET
            service_id = (
                SELECT service_id FROM journal_line_splits
                WHERE journal_line_splits.journal_line_id = journal_lines.id
                ORDER BY created_at ASC
                LIMIT 1
            ),
            service_assignment_mode = (
                SELECT assignment_mode FROM journal_line_splits
                WHERE journal_line_splits.journal_line_id = journal_lines.id
                ORDER BY created_at ASC
                LIMIT 1
            ),
            service_amount_consistency_ok = COALESCE((
                SELECT amount_consistency_ok FROM journal_line_splits
                WHERE journal_line_splits.journal_line_id = journal_lines.id
                ORDER BY created_at ASC
                LIMIT 1
            ), 0)
    """)

    # 3. Neue Tabelle löschen
    op.drop_index("ix_journal_line_splits_service_id", "journal_line_splits")
    op.drop_index("ix_journal_line_splits_journal_line_id", "journal_line_splits")
    op.drop_table("journal_line_splits")
