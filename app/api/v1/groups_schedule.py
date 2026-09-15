from __future__ import annotations

from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    UserPermissionContext,
    require_group_role,
)
from app.db.database import get_db
from app.models.group import Group
from app.models.group_member import MemberRole
from app.models.schedule_new import Lesson, Schedule

router = APIRouter(prefix="/groups", tags=["schedule"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ScheduleCreateRequest(BaseModel):
    """day_of_week: 1 = Monday … 6 = Saturday."""

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
    start_time: str  # "HH:MM"
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# POST /groups/{group_id}/schedules — create a schedule slot for a day
# ---------------------------------------------------------------------------


@router.post(
    "/{group_id}/schedules",
    response_model=ScheduleResponse,
    status_code=201,
)
async def create_schedule(
    group_id: int,
    body: ScheduleCreateRequest,
    ctx: Annotated[
        UserPermissionContext,
        Depends(require_group_role([MemberRole.headman, MemberRole.curator])),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ScheduleResponse:
    """
    Create a schedule entry (group × day_of_week).
    Fails with 409 if this day already has a schedule for the group.
    """
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
            detail=(
                f"Schedule for day {body.day_of_week} "
                f"({_DAY_NAMES.get(body.day_of_week, '?')}) already exists"
            ),
        )

    schedule = Schedule(group_id=group_id, day_of_week=body.day_of_week)
    session.add(schedule)
    await session.flush()

    return ScheduleResponse(
        id=schedule.id,
        group_id=schedule.group_id,
        day_of_week=schedule.day_of_week,
        lessons=[],
    )


# ---------------------------------------------------------------------------
# POST /groups/{group_id}/lessons — add a lesson to a schedule
# ---------------------------------------------------------------------------


@router.post(
    "/{group_id}/lessons",
    response_model=LessonResponse,
    status_code=201,
)
async def add_lesson(
    group_id: int,
    schedule_id: int,
    body: LessonCreateRequest,
    ctx: Annotated[
        UserPermissionContext,
        Depends(require_group_role([MemberRole.headman, MemberRole.curator])),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LessonResponse:
    """
    Add a lesson to a specific schedule slot.
    Requires headman or curator role in the group.
    """
    # Verify schedule belongs to this group
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
    await session.flush()
    return _lesson_to_response(lesson)


# ---------------------------------------------------------------------------
# GET /groups/{group_id}/schedule/today — today's lessons (filtered by date)
# ---------------------------------------------------------------------------


@router.get(
    "/{group_id}/schedule/today",
    response_model=TodayLessonResponse,
)
async def get_today_schedule(
    group_id: int,
    ctx: Annotated[
        UserPermissionContext,
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
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TodayLessonResponse:
    """
    Return today's lessons for the group.

    Filters lessons by:
    - schedule.day_of_week matches today's weekday (ISO: 1=Mon … 7=Sun,
      clamped to 6=Sat for schedules that don't include Sunday)
    - lesson.valid_from <= today (if set)
    - lesson.valid_until >= today (if set)
    """
    today = date.today()
    # Python weekday(): 0=Mon … 6=Sun. Our schema: 1=Mon … 6=Sat.
    iso_dow = today.isoweekday()  # 1=Mon … 7=Sun
    if iso_dow == 7:
        # Sunday — no lessons
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

    # Load lessons valid today
    lesson_result = await session.execute(
        select(Lesson)
        .where(
            Lesson.schedule_id == schedule.id,
            (Lesson.valid_from == None) | (Lesson.valid_from <= today),  # noqa: E711
            (Lesson.valid_until == None) | (Lesson.valid_until >= today),  # noqa: E711
        )
        .order_by(Lesson.lesson_number, Lesson.start_time)
    )
    lessons = [_lesson_to_response(l) for l in lesson_result.scalars().all()]

    return TodayLessonResponse(
        schedule_id=schedule.id,
        day_of_week=iso_dow,
        lessons=lessons,
    )


# ---------------------------------------------------------------------------
# GET /groups/{group_id}/schedule — full week schedule
# ---------------------------------------------------------------------------


@router.get(
    "/{group_id}/schedule",
    response_model=list[ScheduleResponse],
)
async def get_full_schedule(
    group_id: int,
    ctx: Annotated[
        UserPermissionContext,
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
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[ScheduleResponse]:
    """Return the full week schedule for the group, ordered by day_of_week."""
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
