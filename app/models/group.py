from __future__ import annotations

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    tg_chat_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, unique=True
    )
    vk_peer_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, unique=True
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
