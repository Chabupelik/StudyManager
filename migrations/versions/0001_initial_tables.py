"""Initial tables

Revision ID: 0001
Revises:
Create Date: 2026-08-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tg_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tg_id"),
    )
    op.create_index("ix_students_tg_id", "students", ["tg_id"], unique=True)

    op.create_table(
        "attendance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("time", sa.String(5), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "time", "student_id", name="uq_attendance"),
    )
    op.create_index("ix_attendance_date", "attendance", ["date"])
    op.create_index("ix_attendance_student_id", "attendance", ["student_id"])

    op.create_table(
        "overrides",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("time", sa.String(5), nullable=False),
        sa.Column("new_name", sa.String(255), nullable=True),
        sa.Column("new_teacher", sa.String(255), nullable=True),
        sa.Column("is_canceled", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "time", name="uq_override"),
    )
    op.create_index("ix_overrides_date", "overrides", ["date"])

    op.create_table(
        "duties",
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.String(10), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("student_id"),
    )

    op.create_table(
        "web_undos",
        sa.Column("undo_id", sa.String(8), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Double(), nullable=False),
        sa.PrimaryKeyConstraint("undo_id"),
    )

    op.create_table(
        "action_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_name", sa.String(255), nullable=True),
        sa.Column("action_type", sa.String(255), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Double(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_logs_created_at", "action_logs", ["created_at"])
    op.create_index("ix_action_logs_admin_name", "action_logs", ["admin_name"])
    op.create_index("ix_action_logs_action_type", "action_logs", ["action_type"])

    op.create_table(
        "admins_online",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("last_seen", sa.Double(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "message_bridge",
        sa.Column("tg_msg_id", sa.BigInteger(), nullable=False),
        sa.Column("vk_msg_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.Double(), nullable=True),
        sa.PrimaryKeyConstraint("tg_msg_id"),
    )


def downgrade() -> None:
    op.drop_table("message_bridge")
    op.drop_table("admins_online")
    op.drop_table("action_logs")
    op.drop_table("web_undos")
    op.drop_table("duties")
    op.drop_table("overrides")
    op.drop_table("attendance")
    op.drop_table("students")
