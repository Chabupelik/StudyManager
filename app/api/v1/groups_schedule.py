from __future__ import annotations

from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_group_role
from app.db.database import DbSession
from app.models.group import Group
from app.models.group_member import MemberRole
from app.models.schedule_new import Lesson, Schedule
from app.services.user_service import AuthUser

router = APIRouter(prefix="/groups", tags=["schedule"])


class ScheduleCreateRequest(BaseModel):
    day_of_week: int = Field(..., ge=1, le=6)


class LessonCreateRequest(BaseModel):
    lesson_number: int = Field(..., ge=1, le=12)
    name: str = Field(..., min_length=1, max_length=255)
    teacher: str | None = Field(None, max_length=255)
    classroom: str | None = Field(None, max_length=50)
    start_time: time
    end_time: time
    valid_from: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def validate_times(self) -> LessonCreateRequest:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must be >= valid_from")
        return self


class LessonResponse(BaseModel):
    id: int
    lesson_number: int
    name: str
    teacher: str | None
    classroom: str | None
    start_time: str
    end_time: str
    valid_from: date | None
    valid_until: date | None


class ScheduleResponse(BaseModel):
    id: int
    group_id: int
    day_of_week: int
    lessons: list[LessonResponse]


class TodayLessonResponse(BaseModel):
    schedule_id: int
    day_of_week: int
    lessons: list[LessonResponse]


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


async def _get_lessons_for_schedule(
    session: AsyncSession, schedule_id: int
) -> list[LessonResponse]:
    result = await session.execute(
        select(Lesson)
        .where(Lesson.schedule_id == schedule_id)
        .order_by(Lesson.lesson_number, Lesson.start_time)
    )
    return [_lesson_to_response(l) for l in result.scalars().all()]


@router.post(
    "/{group_id}/schedules",
    response_model=ScheduleResponse,
    status_code=201,
)
async def create_schedule(
    group_id: int,
    body: ScheduleCreateRequest,
    current_user: Annotated[
        AuthUser,
        Depends(require_group_role([MemberRole.headman, MemberRole.curator])),
    ],
    session: DbSession,
) -> ScheduleResponse:
    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    existing = await session.execute(
        select(Schedule).where(
            Schedule.group_id == group_id,
            Schedule.day_of_week == body.day_of_week,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Schedule for day {body.day_of_week} ({_DAY_NAMES.get(body.day_of_week, '?')}) already exists for this group",
        )

    sched = Schedule(
        group_id=group_id,
        day_of_week=body.day_of_week,
    )
    session.add(sched)
    await session.commit()
    await session.refresh(sched)
    return ScheduleResponse(
        id=sched.id,
        group_id=sched.group_id,
        day_of_week=sched.day_of_week,
        lessons=[],
    )


@router.post(
    "/{group_id}/schedules/{schedule_id}/lessons",
    response_model=LessonResponse,
    status_code=201,
)
async def add_lesson(
    group_id: int,
    schedule_id: int,
    body: LessonCreateRequest,
    current_user: Annotated[
        AuthUser,
        Depends(require_group_role([MemberRole.headman, MemberRole.curator])),
    ],
    session: DbSession,
) -> LessonResponse:
    schedule = await session.get(Schedule, schedule_id)
    if schedule is None or schedule.group_id != group_id:
        raise HTTPException(status_code=404, detail="Schedule not found in this group")

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
    session.add(lesson)
    await session.commit()
    await session.refresh(lesson)
    return _lesson_to_response(lesson)


@router.get(
    "/{group_id}/schedule/today",
    response_model=TodayLessonResponse,
)
async def get_today_schedule(
    group_id: int,
    current_user: Annotated[
        AuthUser,
        Depends(
            require_group_role(
                [
                    MemberRole.student,
                    MemberRole.deputy,
                    MemberRole.headman,
                    MemberRole.curator,
                ]
            )
        ),
    ],
    session: DbSession,
) -> TodayLessonResponse:
    today = date.today()
    iso_dow = today.isoweekday()
    if iso_dow == 7:
        return TodayLessonResponse(schedule_id=0, day_of_week=7, lessons=[])

    schedule_result = await session.execute(
        select(Schedule).where(
            Schedule.group_id == group_id,
            Schedule.day_of_week == iso_dow,
        )
    )
    schedule = schedule_result.scalar_one_or_none()
    if schedule is None:
        return TodayLessonResponse(schedule_id=0, day_of_week=iso_dow, lessons=[])

    lesson_result = await session.execute(
        select(Lesson)
        .where(
            Lesson.schedule_id == schedule.id,
            (Lesson.valid_from.is_(None)) | (Lesson.valid_from <= today),
            (Lesson.valid_until.is_(None)) | (Lesson.valid_until >= today),
        )
        .order_by(Lesson.lesson_number, Lesson.start_time)
    )
    lessons = [_lesson_to_response(l) for l in lesson_result.scalars().all()]

    return TodayLessonResponse(
        schedule_id=schedule.id,
        day_of_week=iso_dow,
        lessons=lessons,
    )


@router.get(
    "/{group_id}/schedule",
    response_model=list[ScheduleResponse],
)
async def get_full_schedule(
    group_id: int,
    current_user: Annotated[
        AuthUser,
        Depends(
            require_group_role(
                [
                    MemberRole.student,
                    MemberRole.deputy,
                    MemberRole.headman,
                    MemberRole.curator,
                ]
            )
        ),
    ],
    session: DbSession,
) -> list[ScheduleResponse]:
    result = await session.execute(
        select(Schedule)
        .where(Schedule.group_id == group_id)
        .order_by(Schedule.day_of_week)
    )
    schedules = result.scalars().all()

    out = []
    for sched in schedules:
        lessons = await _get_lessons_for_schedule(session, sched.id)
        out.append(
            ScheduleResponse(
                id=sched.id,
                group_id=sched.group_id,
                day_of_week=sched.day_of_week,
                lessons=lessons,
            )
        )
    return out
