"""add service assignment fields and typed review item uniqueness

Revision ID: 017
Revises: 016
Create Date: 2026-04-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("journal_lines") as batch_op:
        batch_op.add_column(sa.Column("service_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("service_assignment_mode", sa.String(length=20), nullable=True))
        batch_op.create_foreign_key(
            "fk_journal_lines_service",
            "services",
            ["service_id"],
            ["id"],
        )
        batch_op.create_index("ix_journal_lines_service_id", ["service_id"], unique=False)

    with op.batch_alter_table("review_items") as batch_op:
        batch_op.drop_constraint("uq_review_items_journal_line", type_="unique")
        batch_op.alter_column("journal_line_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.add_column(sa.Column("service_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch_op.create_foreign_key(
            "fk_review_items_service",
            "services",
            ["service_id"],
            ["id"],
        )
        batch_op.create_index("ix_review_items_journal_line_id", ["journal_line_id"], unique=False)
        batch_op.create_index("ix_review_items_service_id", ["service_id"], unique=False)
        batch_op.create_unique_constraint(
            "uq_review_items_journal_line_item_type",
            ["journal_line_id", "item_type"],
        )
        batch_op.create_unique_constraint(
            "uq_review_items_service_item_type",
            ["service_id", "item_type"],
        )


def downgrade() -> None:
    with op.batch_alter_table("review_items") as batch_op:
        batch_op.drop_constraint("uq_review_items_service_item_type", type_="unique")
        batch_op.drop_constraint("uq_review_items_journal_line_item_type", type_="unique")
        batch_op.drop_index("ix_review_items_service_id")
        batch_op.drop_index("ix_review_items_journal_line_id")
        batch_op.drop_constraint("fk_review_items_service", type_="foreignkey")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("service_id")
        batch_op.alter_column("journal_line_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.create_unique_constraint("uq_review_items_journal_line", ["journal_line_id"])

    with op.batch_alter_table("journal_lines") as batch_op:
        batch_op.drop_index("ix_journal_lines_service_id")
        batch_op.drop_constraint("fk_journal_lines_service", type_="foreignkey")
        batch_op.drop_column("service_assignment_mode")
        batch_op.drop_column("service_id")