from __future__ import annotations

from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import DbSession
from app.models.group_member import MemberRole
from app.models.schedule_new import Lesson
from app.repositories.group_repo import GroupRepository
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.groups_schedule import (
    LessonCreateRequest,
    LessonResponse,
    ScheduleCreateRequest,
    ScheduleResponse,
    TodayLessonResponse,
)
from app.services.user_service import AuthUser

MSK = ZoneInfo("Europe/Moscow")
_DAY_NAMES = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}


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

    def _check_can_view(self, group_id: int, user: AuthUser) -> None:
        if user.is_superadmin:
            return
        role = (user.groups_roles or {}).get(str(group_id))
        if not role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: not a member of this group",
            )

    def _check_can_manage(self, group_id: int, user: AuthUser) -> None:
        if user.is_superadmin:
            return
        role = (user.groups_roles or {}).get(str(group_id))
        if role not in (MemberRole.headman.value, MemberRole.curator.value):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: insufficient permissions in this group",
            )

    async def create_schedule(
        self,
        group_id: int,
        body: ScheduleCreateRequest,
        current_user: AuthUser,
    ) -> ScheduleResponse:
        self._check_can_manage(group_id, current_user)
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

        sched = await self.schedule_repo.create_schedule(
            group_id=group_id,
            day_of_week=body.day_of_week,
        )
        await self.session.commit()
        await self.schedule_repo.refresh(sched)
        return ScheduleResponse(
            id=sched.id,
            group_id=sched.group_id,
            day_of_week=sched.day_of_week,
            lessons=[],
        )

    async def add_lesson(
        self,
        group_id: int,
        schedule_id: int,
        body: LessonCreateRequest,
        current_user: AuthUser,
    ) -> LessonResponse:
        self._check_can_manage(group_id, current_user)
        if body.end_time <= body.start_time:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="end_time must be after start_time",
            )
        if body.valid_from and body.valid_until and body.valid_until < body.valid_from:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="valid_until must be >= valid_from",
            )

        schedule = await self.schedule_repo.get_by_id(schedule_id)
        if schedule is None or schedule.group_id != group_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule not found in this group",
            )

        lesson = await self.schedule_repo.create_lesson(
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
        await self.session.commit()
        await self.schedule_repo.refresh_lesson(lesson)
        return _lesson_to_response(lesson)

    async def get_today_schedule(
        self, group_id: int, current_user: AuthUser
    ) -> TodayLessonResponse:
        self._check_can_view(group_id, current_user)
        today = datetime.now(MSK).date()
        dow = today.weekday()
        if dow == 6:
            return TodayLessonResponse(schedule_id=0, day_of_week=6, lessons=[])

        schedule = await self.schedule_repo.get_by_group_and_day(group_id, dow)
        if schedule is None:
            return TodayLessonResponse(schedule_id=0, day_of_week=dow, lessons=[])

        lessons = await self.schedule_repo.get_active_lessons_for_date(
            schedule.id, today
        )
        return TodayLessonResponse(
            schedule_id=schedule.id,
            day_of_week=dow,
            lessons=[_lesson_to_response(l) for l in lessons],
        )

    async def get_full_schedule(
        self, group_id: int, current_user: AuthUser
    ) -> list[ScheduleResponse]:
        self._check_can_view(group_id, current_user)
        schedules = await self.schedule_repo.get_all_for_group(group_id)
        if not schedules:
            return []

        schedule_ids = [sched.id for sched in schedules]
        all_lessons = await self.schedule_repo.get_lessons_for_schedules(schedule_ids)

        lessons_by_schedule: dict[int, list[Lesson]] = {sid: [] for sid in schedule_ids}
        for l in all_lessons:
            lessons_by_schedule[l.schedule_id].append(l)

        return [
            ScheduleResponse(
                id=sched.id,
                group_id=sched.group_id,
                day_of_week=sched.day_of_week,
                lessons=[
                    _lesson_to_response(l)
                    for l in sorted(
                        lessons_by_schedule.get(sched.id, []),
                        key=lambda x: (x.lesson_number, x.start_time),
                    )
                ],
            )
            for sched in schedules
        ]


def get_groups_schedule_service(db: DbSession) -> GroupsScheduleService:
    return GroupsScheduleService(
        session=db,
        schedule_repo=ScheduleRepository(db),
        group_repo=GroupRepository(db),
    )


GroupsScheduleSrv = Annotated[
    GroupsScheduleService, Depends(get_groups_schedule_service)
]
