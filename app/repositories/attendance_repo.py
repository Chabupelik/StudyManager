from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.attendance import Attendance
from app.repositories.base import BaseRepository


class AttendanceRepository(BaseRepository):
    async def upsert(
        self,
        group_id: int,
        date: str,
        time: str,
        user_id: int,
        status: int,
        reason: str,
    ) -> None:
        stmt = pg_insert(Attendance).values(
            group_id=group_id,
            date=date,
            time=time,
            user_id=user_id,
            status=status,
            reason=reason,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_attendance",
            set_={"status": stmt.excluded.status, "reason": stmt.excluded.reason},
        )
        await self.session.execute(stmt)

    async def get_for_lesson(
        self, group_id: int, date: str, time: str
    ) -> list[Attendance]:
        result = await self.session.execute(
            select(Attendance).where(
                Attendance.group_id == group_id,
                Attendance.date == date,
                Attendance.time == time,
            )
        )
        return list(result.scalars().all())

    async def get_for_date(self, group_id: int, date: str) -> list[Attendance]:
        result = await self.session.execute(
            select(Attendance).where(
                Attendance.group_id == group_id, Attendance.date == date
            )
        )
        return list(result.scalars().all())

    async def get_student_absences(
        self, group_id: int, user_id: int
    ) -> list[Attendance]:
        result = await self.session.execute(
            select(Attendance).where(
                Attendance.group_id == group_id,
                Attendance.user_id == user_id,
                Attendance.status > 0,
            )
        )
        return list(result.scalars().all())

    async def get_absent_count_by_time(
        self, group_id: int, date: str
    ) -> dict[str, int]:
        result = await self.session.execute(
            select(Attendance.time, func.count(Attendance.id))
            .where(
                Attendance.group_id == group_id,
                Attendance.date == date,
                Attendance.status > 0,
            )
            .group_by(Attendance.time)
        )
        return {row[0]: row[1] for row in result.all()}

    async def delete_for_lesson(self, group_id: int, date: str, time: str) -> None:
        await self.session.execute(
            delete(Attendance).where(
                Attendance.group_id == group_id,
                Attendance.date == date,
                Attendance.time == time,
            )
        )

    async def get_all_stats(self, group_id: int) -> list[Attendance]:
        result = await self.session.execute(
            select(Attendance).where(
                Attendance.group_id == group_id, Attendance.status > 0
            )
        )
        return list(result.scalars().all())

    async def get_stats_for_month(
        self, group_id: int, month_prefix: str
    ) -> list[Attendance]:
        result = await self.session.execute(
            select(Attendance).where(
                Attendance.group_id == group_id,
                Attendance.status > 0,
                Attendance.date.like(f"{month_prefix}%"),
            )
        )
        return list(result.scalars().all())
