from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select

from app.models.schedule_new import Lesson, Schedule
from app.repositories.base import BaseRepository


class ScheduleRepository(BaseRepository[Schedule]):
    model = Schedule

    async def get_by_group_and_day(
        self, group_id: int, day_of_week: int
    ) -> Schedule | None:
        result = await self.session.execute(
            select(Schedule).where(
                Schedule.group_id == group_id,
                Schedule.day_of_week == day_of_week,
            )
        )
        return result.scalar_one_or_none()

    async def get_all_for_group(self, group_id: int) -> Sequence[Schedule]:
        result = await self.session.execute(
            select(Schedule)
            .where(Schedule.group_id == group_id)
            .order_by(Schedule.day_of_week)
        )
        return result.scalars().all()

    def add_lesson(self, lesson: Lesson) -> Lesson:
        self.session.add(lesson)
        return lesson

    async def get_lesson_by_id(self, lesson_id: int) -> Lesson | None:
        return await self.session.get(Lesson, lesson_id)

    async def delete_lesson(self, lesson: Lesson) -> None:
        await self.session.delete(lesson)

    async def get_lessons_for_schedule(self, schedule_id: int) -> Sequence[Lesson]:
        result = await self.session.execute(
            select(Lesson)
            .where(Lesson.schedule_id == schedule_id)
            .order_by(Lesson.lesson_number, Lesson.start_time)
        )
        return result.scalars().all()

    async def get_active_lessons_for_date(
        self, schedule_id: int, target_date: date
    ) -> Sequence[Lesson]:
        result = await self.session.execute(
            select(Lesson)
            .where(
                Lesson.schedule_id == schedule_id,
                (Lesson.valid_from.is_(None)) | (Lesson.valid_from <= target_date),
                (Lesson.valid_until.is_(None)) | (Lesson.valid_until >= target_date),
            )
            .order_by(Lesson.lesson_number, Lesson.start_time)
        )
        return result.scalars().all()

    async def get_base_lessons_with_schedules(
        self, group_id: int
    ) -> tuple[Sequence[Schedule], Sequence[Lesson]]:
        stmt_schedules = select(Schedule).where(Schedule.group_id == group_id)
        schedules = (await self.session.execute(stmt_schedules)).scalars().all()

        stmt_lessons = (
            select(Lesson)
            .join(Schedule)
            .where(Schedule.group_id == group_id)
            .order_by(
                Schedule.day_of_week,
                Lesson.valid_from.desc().nulls_first(),
                Lesson.start_time,
            )
        )
        lessons = (await self.session.execute(stmt_lessons)).scalars().all()
        return schedules, lessons
