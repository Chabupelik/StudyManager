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

    async def get_by_ids(self, user_ids: list[int]) -> list[User]:
        if not user_ids:
            return []
        result = await self.session.execute(select(User).where(User.id.in_(user_ids)))
        return list(result.scalars().all())

    async def get_by_vk_id(self, vk_user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.vk_user_id == vk_user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_external_id(
        self,
        tg_user_id: int | None = None,
        vk_user_id: int | None = None,
    ) -> User | None:
        if tg_user_id is not None:
            user = await self.get_by_tg_id(tg_user_id)
            if user is not None:
                return user
        if vk_user_id is not None:
            return await self.get_by_vk_id(vk_user_id)
        return None

    async def get_by_tg_id_excluding(
        self, tg_user_id: int, exclude_user_id: int
    ) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.tg_user_id == tg_user_id,
                User.id != exclude_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_vk_id_excluding(
        self, vk_user_id: int, exclude_user_id: int
    ) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.vk_user_id == vk_user_id,
                User.id != exclude_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        full_name: str,
        tg_user_id: int | None = None,
        vk_user_id: int | None = None,
    ) -> User:
        user = User(
            full_name=full_name,
            tg_user_id=tg_user_id,
            vk_user_id=vk_user_id,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(
        self,
        user: User,
        full_name: str | None = None,
        tg_user_id: int | None = None,
        vk_user_id: int | None = None,
    ) -> User:
        if full_name is not None:
            user.full_name = full_name
        if tg_user_id is not None:
            user.tg_user_id = tg_user_id
        if vk_user_id is not None:
            user.vk_user_id = vk_user_id
        await self.session.flush()
        return user

    async def get_group_students(
        self, group_id: int, exclude_duty_exempt: bool = False
    ) -> list[User]:
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
        if exclude_duty_exempt:
            stmt = stmt.where(GroupMember.is_duty_exempt.is_(False))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
