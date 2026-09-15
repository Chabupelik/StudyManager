from __future__ import annotations

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Schedule(Base):
    """Расписание группы на конкретный день недели (1=Пн … 6=Сб)."""

    __tablename__ = "schedules"
    __table_args__ = (UniqueConstraint("group_id", "day_of_week", name="uq_group_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_of_week: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="1=Monday … 6=Saturday",
    )


class Lesson(Base):
    """Конкретная пара в расписании группы."""

    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lesson_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    teacher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classroom: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_time: Mapped[object] = mapped_column(Time, nullable=False)
    end_time: Mapped[object] = mapped_column(Time, nullable=False)
    valid_from: Mapped[object | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[object | None] = mapped_column(Date, nullable=True)
