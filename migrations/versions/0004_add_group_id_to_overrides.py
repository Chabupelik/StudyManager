"""Add group_id to overrides

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Add group_id column with default value 1 for existing overrides
    op.add_column(
        "overrides",
        sa.Column("group_id", sa.Integer(), nullable=False, server_default="1"),
    )

    # Create index for group_id
    op.create_index(
        op.f("ix_overrides_group_id"), "overrides", ["group_id"], unique=False
    )

    # Create foreign key
    op.create_foreign_key(
        "fk_overrides_group_id",
        "overrides",
        "groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Drop old unique constraint and create new one
    op.drop_constraint("uq_override", "overrides", type_="unique")
    op.create_unique_constraint(
        "uq_override", "overrides", ["date", "time", "group_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_override", "overrides", type_="unique")
    op.create_unique_constraint("uq_override", "overrides", ["date", "time"])

    op.drop_constraint("fk_overrides_group_id", "overrides", type_="foreignkey")
    op.drop_index(op.f("ix_overrides_group_id"), table_name="overrides")
    op.drop_column("overrides", "group_id")
