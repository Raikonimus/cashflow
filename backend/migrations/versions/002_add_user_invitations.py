"""add user_invitations table

Revision ID: 002
Revises: 001
Create Date: 2026-04-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_invitations"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_invitations_user"
        ),
    )
    op.create_index("ix_user_invitations_user_id", "user_invitations", ["user_id"])
    op.create_index(
        "ix_user_invitations_token_hash", "user_invitations", ["token_hash"]
    )


def downgrade() -> None:
    op.drop_table("user_invitations")
