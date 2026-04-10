"""make audit_log.mandant_id nullable for system-level events

Revision ID: 015
Revises: 014
Create Date: 2026-04-08

"""
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("audit_log") as batch_op:
        batch_op.alter_column(
            "mandant_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_log") as batch_op:
        batch_op.alter_column(
            "mandant_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
