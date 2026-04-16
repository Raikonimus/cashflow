"""add service groups and assignments

Revision ID: 022
Revises: 021
Create Date: 2026-04-15

"""
# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context
from alembic.operations import Operations

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    migration_context = getattr(context, "get_context")()
    operations = Operations(migration_context)
    bind = migration_context.bind
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "service_groups" not in table_names:
        operations.create_table(
            "service_groups",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("mandant_id", sa.Uuid(), sa.ForeignKey("mandants.id"), nullable=False),
            sa.Column("section", sa.String(length=20), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("mandant_id", "section", "name", name="uq_service_groups_scope_name"),
        )

    group_indexes = {index["name"] for index in inspector.get_indexes("service_groups")}
    if "ix_service_groups_mandant_id" not in group_indexes:
        operations.create_index("ix_service_groups_mandant_id", "service_groups", ["mandant_id"], unique=False)

    if "service_group_assignments" not in table_names:
        operations.create_table(
            "service_group_assignments",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("mandant_id", sa.Uuid(), sa.ForeignKey("mandants.id"), nullable=False),
            sa.Column("service_id", sa.Uuid(), sa.ForeignKey("services.id"), nullable=False),
            sa.Column("service_group_id", sa.Uuid(), sa.ForeignKey("service_groups.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("service_id", name="uq_service_group_assignments_service"),
        )

    assignment_indexes = {index["name"] for index in inspector.get_indexes("service_group_assignments")}
    if "ix_service_group_assignments_mandant_id" not in assignment_indexes:
        operations.create_index("ix_service_group_assignments_mandant_id", "service_group_assignments", ["mandant_id"], unique=False)
    if "ix_service_group_assignments_service_id" not in assignment_indexes:
        operations.create_index("ix_service_group_assignments_service_id", "service_group_assignments", ["service_id"], unique=False)
    if "ix_service_group_assignments_service_group_id" not in assignment_indexes:
        operations.create_index("ix_service_group_assignments_service_group_id", "service_group_assignments", ["service_group_id"], unique=False)


def downgrade() -> None:
    migration_context = getattr(context, "get_context")()
    operations = Operations(migration_context)
    bind = migration_context.bind
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "service_group_assignments" in table_names:
        assignment_indexes = {index["name"] for index in inspector.get_indexes("service_group_assignments")}
        if "ix_service_group_assignments_service_group_id" in assignment_indexes:
            operations.drop_index("ix_service_group_assignments_service_group_id", table_name="service_group_assignments")
        if "ix_service_group_assignments_service_id" in assignment_indexes:
            operations.drop_index("ix_service_group_assignments_service_id", table_name="service_group_assignments")
        if "ix_service_group_assignments_mandant_id" in assignment_indexes:
            operations.drop_index("ix_service_group_assignments_mandant_id", table_name="service_group_assignments")
        operations.drop_table("service_group_assignments")

    if "service_groups" in table_names:
        group_indexes = {index["name"] for index in inspector.get_indexes("service_groups")}
        if "ix_service_groups_mandant_id" in group_indexes:
            operations.drop_index("ix_service_groups_mandant_id", table_name="service_groups")
        operations.drop_table("service_groups")
