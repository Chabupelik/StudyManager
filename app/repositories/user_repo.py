from __future__ import annotations

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_tg_id(self, tg_user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.tg_user_id == tg_user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_vk_id(self, vk_user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.vk_user_id == vk_user_id)
        )
        return result.scalar_one_or_none()
