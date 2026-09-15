from __future__ import annotations

import enum

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MemberRole(enum.StrEnum):
    student = "student"
    deputy = "deputy"
    headman = "headman"
    curator = "curator"


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_user_group"),
        Index("ix_group_members_user_group", "user_id", "group_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        sa.Enum(
            MemberRole,
            name="member_role",
            native_enum=False,
            length=20,
        ),
        nullable=False,
    )
