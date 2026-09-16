from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Duty(Base):
    __tablename__ = "duties"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_user_duty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[str | None] = mapped_column(String(10), nullable=True)


class WebUndo(Base):
    __tablename__ = "web_undos"

    undo_id: Mapped[str] = mapped_column(String(8), primary_key=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(nullable=False)
