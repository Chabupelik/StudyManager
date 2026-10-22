from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User


class UserContext:
    __slots__ = ("first_name", "id", "platform", "username")

    def __init__(
        self,
        id: int,
        first_name: str = "",
        username: str | None = None,
        platform: str = "web",
    ) -> None:
        self.id = id
        self.first_name = first_name
        self.username = username
        self.platform = platform

    @property
    def is_developer(self) -> bool:
        return self.id == get_settings().developer_id


_tg_id_to_name: dict[int, str] = {}


def get_display_name(user: UserContext) -> str:
    name = _tg_id_to_name.get(user.id)
    if name:
        return name
    return user.first_name or f"Пользователь {user.id}"


async def refresh_user_cache_entry(tg_user_id: int, session: AsyncSession) -> None:
    if tg_user_id in _tg_id_to_name:
        return

    result = await session.execute(select(User).where(User.tg_user_id == tg_user_id))
    user_obj = result.scalar_one_or_none()
    if user_obj and user_obj.full_name:
        _tg_id_to_name[tg_user_id] = user_obj.full_name
