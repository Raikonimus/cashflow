"""add partner management tables

Revision ID: 004
Revises: 003
Create Date: 2026-04-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # partners
    # ------------------------------------------------------------------
    op.create_table(
        "partners",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_partners"),
        sa.UniqueConstraint("mandant_id", "name", name="uq_partners_mandant_name"),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandants.id"], name="fk_partners_mandant", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_partners_mandant_id", "partners", ["mandant_id"])

    # ------------------------------------------------------------------
    # partner_ibans
    # ------------------------------------------------------------------
    op.create_table(
        "partner_ibans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("iban", sa.String(34), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_partner_ibans"),
        sa.UniqueConstraint("iban", name="uq_partner_ibans_iban"),
        sa.ForeignKeyConstraint(
            ["partner_id"], ["partners.id"], name="fk_partner_ibans_partner", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_partner_ibans_partner_id", "partner_ibans", ["partner_id"])

    # ------------------------------------------------------------------
    # partner_names
    # ------------------------------------------------------------------
    op.create_table(
        "partner_names",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_partner_names"),
        sa.UniqueConstraint("partner_id", "name", name="uq_partner_names_partner_name"),
        sa.ForeignKeyConstraint(
            ["partner_id"], ["partners.id"], name="fk_partner_names_partner", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_partner_names_partner_id", "partner_names", ["partner_id"])

    # ------------------------------------------------------------------
    # partner_patterns
    # ------------------------------------------------------------------
    op.create_table(
        "partner_patterns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pattern", sa.String(500), nullable=False),
        sa.Column("pattern_type", sa.String(10), nullable=False),
        sa.Column("match_field", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_partner_patterns"),
        sa.UniqueConstraint(
            "partner_id", "pattern", "match_field", name="uq_partner_patterns_combo"
        ),
        sa.CheckConstraint("pattern_type IN ('string', 'regex')", name="ck_partner_patterns_type"),
        sa.CheckConstraint(
            "match_field IN ('description', 'partner_name', 'partner_iban')",
            name="ck_partner_patterns_match_field",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"], ["partners.id"], name="fk_partner_patterns_partner", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_partner_patterns_partner_id", "partner_patterns", ["partner_id"])


def downgrade() -> None:
    op.drop_index("ix_partner_patterns_partner_id", table_name="partner_patterns")
    op.drop_table("partner_patterns")
    op.drop_index("ix_partner_names_partner_id", table_name="partner_names")
    op.drop_table("partner_names")
    op.drop_index("ix_partner_ibans_partner_id", table_name="partner_ibans")
    op.drop_table("partner_ibans")
    op.drop_index("ix_partners_mandant_id", table_name="partners")
    op.drop_table("partners")
