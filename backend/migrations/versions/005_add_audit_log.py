"""add audit_log table

Revision ID: 005
Revises: 004
Create Date: 2026-04-06

"""
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


json_type = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()), "postgresql"
)


def upgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mandant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.ForeignKeyConstraint(
            ["mandant_id"], ["mandants.id"], name="fk_audit_log_mandant", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name="fk_audit_log_actor"
        ),
    )
    operations.create_index("ix_audit_log_mandant_id", "audit_log", ["mandant_id"])
    operations.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    operations.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])


def downgrade() -> None:
    operations = Operations(getattr(context, "get_context")())

    operations.drop_index("ix_audit_log_event_type", table_name="audit_log")
    operations.drop_index("ix_audit_log_created_at", table_name="audit_log")
    operations.drop_index("ix_audit_log_mandant_id", table_name="audit_log")
    operations.drop_table("audit_log")
