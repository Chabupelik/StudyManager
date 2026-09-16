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

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Use raw SQL with IF NOT EXISTS guards so the migration is safe to
    # re-run if a previous attempt partially committed DDL.

    # 1. Add column (idempotent)
    op.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS user_id INTEGER")

    # 2. FK constraint — only add if it does not already exist
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_attendance_user_id'
            ) THEN
                ALTER TABLE attendance
                    ADD CONSTRAINT fk_attendance_user_id
                    FOREIGN KEY (user_id) REFERENCES users(id)
                    ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )

    # 3. Back-fill: link via students.tg_id = users.tg_user_id
    op.execute(
        """
        UPDATE attendance AS a
        SET user_id = u.id
        FROM students AS s
        JOIN users AS u ON u.tg_user_id = s.tg_id
        WHERE s.id = a.student_id
          AND a.student_id IS NOT NULL
          AND a.user_id IS NULL
        """
    )

    # 4. Index (idempotent)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_attendance_user_id ON attendance(user_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_user_id", table_name="attendance")
    op.drop_constraint("fk_attendance_user_id", "attendance", type_="foreignkey")
    op.drop_column("attendance", "user_id")
