"""add service management tables

Revision ID: 016
Revises: 015
Create Date: 2026-04-10

"""
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context
from alembic.operations import Operations

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.create_table(
        "services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("service_type", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="20.00"),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_base_service", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("service_type_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tax_rate_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "name", name="uq_services_partner_name"),
    )
    operations.create_index("ix_services_partner_id", "services", ["partner_id"])

    operations.create_table(
        "service_matchers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("pattern", sa.String(length=500), nullable=False),
        sa.Column("pattern_type", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "pattern", "pattern_type", name="uq_service_matchers_service_pattern"),
    )
    operations.create_index("ix_service_matchers_service_id", "service_matchers", ["service_id"])

    operations.create_table(
        "service_type_keywords",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mandant_id", sa.Uuid(), nullable=True),
        sa.Column("pattern", sa.String(length=500), nullable=False),
        sa.Column("pattern_type", sa.String(length=10), nullable=False),
        sa.Column("target_service_type", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["mandant_id"], ["mandants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mandant_id",
            "pattern",
            "pattern_type",
            "target_service_type",
            name="uq_service_type_keywords_scope_pattern",
        ),
    )
    operations.create_index("ix_service_type_keywords_mandant_id", "service_type_keywords", ["mandant_id"])


def downgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.drop_index("ix_service_type_keywords_mandant_id", "service_type_keywords")
    operations.drop_table("service_type_keywords")
    operations.drop_index("ix_service_matchers_service_id", "service_matchers")
    operations.drop_table("service_matchers")
    operations.drop_index("ix_services_partner_id", "services")
    operations.drop_table("services")
