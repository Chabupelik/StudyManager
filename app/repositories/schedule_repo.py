from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time

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

    async def create_schedule(self, group_id: int, day_of_week: int) -> Schedule:
        sched = Schedule(group_id=group_id, day_of_week=day_of_week)
        self.session.add(sched)
        await self.session.flush()
        return sched

    async def get_or_create_schedule(self, group_id: int, day_of_week: int) -> Schedule:
        sched = await self.get_by_group_and_day(group_id, day_of_week)
        if sched is None:
            sched = await self.create_schedule(group_id, day_of_week)
        return sched

    def add_lesson(self, lesson: Lesson) -> Lesson:
        self.session.add(lesson)
        return lesson

    async def create_lesson(
        self,
        schedule_id: int,
        lesson_number: int,
        name: str,
        start_time: time,
        end_time: time,
        teacher: str | None = None,
        classroom: str | None = None,
        valid_from: date | None = None,
        valid_until: date | None = None,
    ) -> Lesson:
        lesson = Lesson(
            schedule_id=schedule_id,
            lesson_number=lesson_number,
            name=name,
            teacher=teacher,
            classroom=classroom,
            start_time=start_time,
            end_time=end_time,
            valid_from=valid_from,
            valid_until=valid_until,
        )
        self.session.add(lesson)
        await self.session.flush()
        return lesson

    async def update_lesson(self, lesson: Lesson, data: dict) -> Lesson:
        if "name" in data:
            lesson.name = data["name"]
        if "teacher" in data:
            lesson.teacher = data["teacher"]
        if "classroom" in data:
            lesson.classroom = data["classroom"]
        if "lesson_number" in data:
            lesson.lesson_number = data["lesson_number"]
        if "start_time" in data:
            lesson.start_time = datetime.strptime(data["start_time"], "%H:%M").time()
        if "end_time" in data:
            lesson.end_time = datetime.strptime(data["end_time"], "%H:%M").time()
        if "valid_from" in data:
            lesson.valid_from = (
                datetime.strptime(data["valid_from"], "%Y-%m-%d").date()
                if data["valid_from"]
                else None
            )
        if "valid_until" in data:
            lesson.valid_until = (
                datetime.strptime(data["valid_until"], "%Y-%m-%d").date()
                if data["valid_until"]
                else None
            )
        await self.session.flush()
        return lesson

    async def get_lesson_by_id(self, lesson_id: int) -> Lesson | None:
        return await self.session.get(Lesson, lesson_id)

    async def refresh_lesson(self, lesson: Lesson) -> None:
        await self.session.refresh(lesson)

    async def delete_lesson(self, lesson: Lesson) -> None:
        await self.session.delete(lesson)

    async def get_lessons_for_schedule(self, schedule_id: int) -> Sequence[Lesson]:
        result = await self.session.execute(
            select(Lesson)
            .where(Lesson.schedule_id == schedule_id)
            .order_by(Lesson.lesson_number, Lesson.start_time)
        )
        return result.scalars().all()

    async def get_lessons_for_schedules(
        self, schedule_ids: Sequence[int]
    ) -> Sequence[Lesson]:
        if not schedule_ids:
            return []
        result = await self.session.execute(
            select(Lesson)
            .where(Lesson.schedule_id.in_(schedule_ids))
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

    async def get_base_times_for_date(self, group_id: int, date_str: str) -> set[str]:
        weekday = datetime.strptime(date_str, "%Y-%m-%d").isoweekday()
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

        stmt = (
            select(Lesson.start_time)
            .join(Schedule)
            .where(
                Schedule.group_id == group_id,
                Schedule.day_of_week == weekday,
                (Lesson.valid_from <= date_obj) | (Lesson.valid_from.is_(None)),
                (Lesson.valid_until >= date_obj) | (Lesson.valid_until.is_(None)),
            )
        )
        result = await self.session.execute(stmt)
        times = result.scalars().all()
        return {t.strftime("%H:%M") for t in times}

    async def get_base_lessons_for_date(
        self, group_id: int, date_str: str
    ) -> Sequence[Lesson]:
        weekday = datetime.strptime(date_str, "%Y-%m-%d").isoweekday()
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

        stmt = (
            select(Lesson)
            .join(Schedule)
            .where(
                Schedule.group_id == group_id,
                Schedule.day_of_week == weekday,
                (Lesson.valid_from <= date_obj) | (Lesson.valid_from.is_(None)),
                (Lesson.valid_until >= date_obj) | (Lesson.valid_until.is_(None)),
            )
            .order_by(Lesson.start_time)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_teacher_for_lesson_name(
        self, group_id: int, lesson_name: str
    ) -> str | None:
        stmt = (
            select(Lesson.teacher)
            .join(Schedule)
            .where(Schedule.group_id == group_id, Lesson.name == lesson_name)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_lesson_at_time(
        self, group_id: int, weekday: int, time_obj: time, date_obj: date
    ) -> Lesson | None:
        stmt = (
            select(Lesson)
            .join(Schedule)
            .where(
                Schedule.group_id == group_id,
                Schedule.day_of_week == weekday,
                Lesson.start_time == time_obj,
                (Lesson.valid_from <= date_obj) | (Lesson.valid_from.is_(None)),
                (Lesson.valid_until >= date_obj) | (Lesson.valid_until.is_(None)),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
