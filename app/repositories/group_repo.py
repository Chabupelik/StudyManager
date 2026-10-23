from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select

from app.models.attendance import Attendance
from app.models.duty import Duty
from app.models.group import Group
from app.repositories.base import BaseRepository


class GroupRepository(BaseRepository[Group]):
    model = Group

    async def get_by_name(self, name: str) -> Group | None:
        result = await self.session.execute(select(Group).where(Group.name == name))
        return result.scalar_one_or_none()

    async def get_all_ordered_by_name(self) -> Sequence[Group]:
        result = await self.session.execute(select(Group).order_by(Group.name))
        return result.scalars().all()

    async def get_by_ids_ordered_by_name(
        self, group_ids: Sequence[int]
    ) -> Sequence[Group]:
        result = await self.session.execute(
            select(Group).where(Group.id.in_(group_ids)).order_by(Group.name)
        )
        return result.scalars().all()

    async def delete_group_related_data(self, group_id: int) -> None:
        await self.session.execute(
            delete(Attendance).where(Attendance.group_id == group_id)
        )
        await self.session.execute(delete(Duty).where(Duty.group_id == group_id))
