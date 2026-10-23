from __future__ import annotations

from sqlalchemy import select

from app.models.group_member import GroupMember, MemberRole
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

    async def get_group_students(self, group_id: int) -> list[User]:
        stmt = (
            select(User)
            .join(GroupMember, GroupMember.user_id == User.id)
            .where(
                GroupMember.group_id == group_id,
                GroupMember.role.in_(
                    [MemberRole.student, MemberRole.headman, MemberRole.deputy]
                ),
            )
            .order_by(User.full_name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
