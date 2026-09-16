from __future__ import annotations

import json
import time

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.duty import Duty, WebUndo
from app.repositories.base import BaseRepository


class DutyRepository(BaseRepository):
    async def get_all(self, group_id: int) -> dict[int, str | None]:
        result = await self.session.execute(
            select(Duty).where(Duty.group_id == group_id)
        )
        return {row.user_id: row.date for row in result.scalars().all()}

    async def upsert(self, group_id: int, user_id: int, date: str) -> None:
        stmt = pg_insert(Duty).values(group_id=group_id, user_id=user_id, date=date)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_group_user_duty",
            set_={"date": stmt.excluded.date},
        )
        await self.session.execute(stmt)

    async def restore(self, group_id: int, user_id: int, date: str | None) -> None:
        if date is None:
            await self.session.execute(
                delete(Duty).where(Duty.group_id == group_id, Duty.user_id == user_id)
            )
        else:
            await self.upsert(group_id, user_id, date)

    async def save_undo(self, undo_id: str, undo_data: list) -> None:
        undo = WebUndo(
            undo_id=undo_id, data=json.dumps(undo_data), created_at=time.time()
        )
        self.session.add(undo)

    async def pop_undo(self, undo_id: str) -> list | None:
        result = await self.session.execute(
            select(WebUndo).where(WebUndo.undo_id == undo_id)
        )
        undo = result.scalar_one_or_none()
        if not undo:
            return None
        data = json.loads(undo.data)
        await self.session.delete(undo)
        return data
