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

    async def create(
        self,
        name: str,
        tg_chat_id: int | None = None,
        vk_peer_id: int | None = None,
    ) -> Group:
        group = Group(name=name, tg_chat_id=tg_chat_id, vk_peer_id=vk_peer_id)
        self.session.add(group)
        await self.session.flush()
        return group

    async def update(
        self,
        group: Group,
        name: str | None = None,
        tg_chat_id: int | None = None,
        vk_peer_id: int | None = None,
    ) -> Group:
        if name is not None:
            group.name = name
        if tg_chat_id is not None:
            group.tg_chat_id = tg_chat_id
        if vk_peer_id is not None:
            group.vk_peer_id = vk_peer_id
        await self.session.flush()
        return group

    async def delete_group(self, group: Group) -> None:
        await self.delete_group_related_data(group.id)
        await self.session.delete(group)
