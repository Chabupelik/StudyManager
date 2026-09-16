"""Add user_id to attendance (bridge from students.id to users.id)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16

Strategy
--------
1. Add nullable column  attendance.user_id  →  users.id
2. Back-fill via JOIN:  students.tg_id  =  users.tg_user_id
3. Rows without a match keep user_id = NULL (no data loss).
4. student_id remains untouched — existing code keeps working.
   Removing student_id is a separate future step.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. Add new column (nullable so it doesn't break rows that can't be matched)
    op.add_column(
        "attendance",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )

    # 2. Create FK constraint (deferred so the NULL rows don't violate it)
    op.create_foreign_key(
        "fk_attendance_user_id",
        "attendance",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. Back-fill: match via tg_id linkage
    #    students.tg_id == users.tg_user_id → attendance.student_id == students.id
    op.execute(
        """
        UPDATE attendance AS a
        SET user_id = u.id
        FROM students AS s
        JOIN users AS u ON u.tg_user_id = s.tg_id
        WHERE s.id = a.student_id
          AND a.student_id IS NOT NULL
        """
    )

    # 4. Index for future queries by user_id
    op.create_index("ix_attendance_user_id", "attendance", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_attendance_user_id", table_name="attendance")
    op.drop_constraint("fk_attendance_user_id", "attendance", type_="foreignkey")
    op.drop_column("attendance", "user_id")
