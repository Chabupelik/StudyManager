from sqlalchemy import ForeignKey, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Override(Base):
    __tablename__ = "overrides"
    __table_args__ = (UniqueConstraint("date", "time", "group_id", name="uq_override"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        default=1,
        index=True,
    )
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    time: Mapped[str] = mapped_column(String(5), nullable=False)
    new_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_teacher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_canceled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
