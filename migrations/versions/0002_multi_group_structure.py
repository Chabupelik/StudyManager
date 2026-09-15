"""Add multi-group structure: groups, users, group_members, schedules, lessons

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── groups ──────────────────────────────────────────────────────────────
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("vk_peer_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("tg_chat_id"),
        sa.UniqueConstraint("vk_peer_id"),
    )

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=True),
        sa.Column("vk_user_id", sa.BigInteger(), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column(
            "is_superadmin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tg_user_id"),
        sa.UniqueConstraint("vk_user_id"),
    )
    op.create_index("ix_users_tg_user_id", "users", ["tg_user_id"], unique=True)
    op.create_index("ix_users_vk_user_id", "users", ["vk_user_id"], unique=True)

    # ── group_members ────────────────────────────────────────────────────────
    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        # Roles stored as VARCHAR(20) — no native Postgres ENUM
        # so downgrade() never hits "type does not exist" errors.
        sa.Column("role", sa.VARCHAR(20), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "group_id", name="uq_user_group"),
    )
    op.create_index(
        "ix_group_members_user_group",
        "group_members",
        ["user_id", "group_id"],
    )

    # ── schedules ────────────────────────────────────────────────────────────
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "day_of_week", name="uq_group_day"),
    )
    op.create_index("ix_schedules_group_id", "schedules", ["group_id"])

    # ── lessons ──────────────────────────────────────────────────────────────
    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("lesson_number", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("teacher", sa.String(255), nullable=True),
        sa.Column("classroom", sa.String(50), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lessons_schedule_id", "lessons", ["schedule_id"])


def downgrade() -> None:
    # Drop in reverse dependency order.
    # attendance and overrides are intentionally left untouched.
    op.drop_index("ix_lessons_schedule_id", table_name="lessons")
    op.drop_table("lessons")

    op.drop_index("ix_schedules_group_id", table_name="schedules")
    op.drop_table("schedules")

    op.drop_index("ix_group_members_user_group", table_name="group_members")
    op.drop_table("group_members")

    op.drop_index("ix_users_vk_user_id", table_name="users")
    op.drop_index("ix_users_tg_user_id", table_name="users")
    op.drop_table("users")

    op.drop_table("groups")
