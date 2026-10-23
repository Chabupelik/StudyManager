from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.models.group_member import GroupMember
from app.models.user import User
from app.repositories.base import BaseRepository


class GroupMemberRepository(BaseRepository[GroupMember]):
    model = GroupMember

    async def get_members_with_users(
        self, group_id: int
    ) -> Sequence[tuple[User, GroupMember]]:
        stmt = (
            select(User, GroupMember)
            .join(GroupMember, GroupMember.user_id == User.id)
            .where(GroupMember.group_id == group_id)
            .order_by(User.full_name)
        )
        result = await self.session.execute(stmt)
        return result.all()

    async def get_member(self, group_id: int, user_id: int) -> GroupMember | None:
        result = await self.session.execute(
            select(GroupMember).where(
                GroupMember.user_id == user_id,
                GroupMember.group_id == group_id,
            )
        )
        return result.scalar_one_or_none()
