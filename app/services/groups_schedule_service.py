from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import DbSession
from app.models.schedule_new import Lesson, Schedule
from app.repositories.group_repo import GroupRepository
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.groups_schedule import (
    LessonCreateRequest,
    LessonResponse,
    ScheduleCreateRequest,
    ScheduleResponse,
    TodayLessonResponse,
)

_DAY_NAMES = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб"}


def _lesson_to_response(lesson: Lesson) -> LessonResponse:
    return LessonResponse(
        id=lesson.id,
        lesson_number=lesson.lesson_number,
        name=lesson.name,
        teacher=lesson.teacher,
        classroom=lesson.classroom,
        start_time=lesson.start_time.strftime("%H:%M"),
        end_time=lesson.end_time.strftime("%H:%M"),
        valid_from=lesson.valid_from,
        valid_until=lesson.valid_until,
    )


class GroupsScheduleService:
    def __init__(
        self,
        session: AsyncSession,
        schedule_repo: ScheduleRepository,
        group_repo: GroupRepository,
    ) -> None:
        self.session = session
        self.schedule_repo = schedule_repo
        self.group_repo = group_repo

    async def create_schedule(
        self, group_id: int, body: ScheduleCreateRequest
    ) -> ScheduleResponse:
        group = await self.group_repo.get_by_id(group_id)
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        existing = await self.schedule_repo.get_by_group_and_day(
            group_id, body.day_of_week
        )
        if existing is not None:
            day_name = _DAY_NAMES.get(body.day_of_week, "?")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Schedule for day {body.day_of_week} ({day_name}) already exists for this group",
            )

        sched = Schedule(
            group_id=group_id,
            day_of_week=body.day_of_week,
        )
        self.schedule_repo.add(sched)
        await self.session.commit()
        await self.session.refresh(sched)
        return ScheduleResponse(
            id=sched.id,
            group_id=sched.group_id,
            day_of_week=sched.day_of_week,
            lessons=[],
        )

    async def add_lesson(
        self, group_id: int, schedule_id: int, body: LessonCreateRequest
    ) -> LessonResponse:
        schedule = await self.schedule_repo.get_by_id(schedule_id)
        if schedule is None or schedule.group_id != group_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule not found in this group",
            )

        lesson = Lesson(
            schedule_id=schedule_id,
            lesson_number=body.lesson_number,
            name=body.name,
            teacher=body.teacher,
            classroom=body.classroom,
            start_time=body.start_time,
            end_time=body.end_time,
            valid_from=body.valid_from,
            valid_until=body.valid_until,
        )
        self.schedule_repo.add_lesson(lesson)
        await self.session.commit()
        await self.session.refresh(lesson)
        return _lesson_to_response(lesson)

    async def get_today_schedule(self, group_id: int) -> TodayLessonResponse:
        today = date.today()
        iso_dow = today.isoweekday()
        if iso_dow == 7:
            return TodayLessonResponse(schedule_id=0, day_of_week=7, lessons=[])

        schedule = await self.schedule_repo.get_by_group_and_day(group_id, iso_dow)
        if schedule is None:
            return TodayLessonResponse(schedule_id=0, day_of_week=iso_dow, lessons=[])

        lessons = await self.schedule_repo.get_active_lessons_for_date(
            schedule.id, today
        )
        return TodayLessonResponse(
            schedule_id=schedule.id,
            day_of_week=iso_dow,
            lessons=[_lesson_to_response(l) for l in lessons],
        )

    async def get_full_schedule(self, group_id: int) -> list[ScheduleResponse]:
        schedules = await self.schedule_repo.get_all_for_group(group_id)
        out = []
        for sched in schedules:
            lessons = await self.schedule_repo.get_lessons_for_schedule(sched.id)
            out.append(
                ScheduleResponse(
                    id=sched.id,
                    group_id=sched.group_id,
                    day_of_week=sched.day_of_week,
                    lessons=[_lesson_to_response(l) for l in lessons],
                )
            )
        return out


def get_groups_schedule_service(db: DbSession) -> GroupsScheduleService:
    return GroupsScheduleService(
        session=db,
        schedule_repo=ScheduleRepository(db),
        group_repo=GroupRepository(db),
    )


GroupsScheduleSrv = Annotated[
    GroupsScheduleService, Depends(get_groups_schedule_service)
]
