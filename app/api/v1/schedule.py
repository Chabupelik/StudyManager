from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    UserPermissionContext,
    get_current_user_context,
    get_request_details,
)
from app.db.database import async_session_maker, get_db
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.override_repo import OverrideRepository
from app.schemas.schedule import OverrideUpdateRequest, ScheduleResponse
from app.services.audit_service import log_action
from app.services.schedule_service import MSK, build_schedule
from app.services.user_service import get_display_name
from app.websocket.manager import manager

router = APIRouter(tags=["schedule"])


def _parse_date(date: str) -> datetime:
    try:
        return datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {date!r}")


async def _log_schedule_action(
    admin_name: str, action_type: str, details: str, user_id: int
) -> None:
    async with async_session_maker() as session:
        await log_action(session, admin_name, action_type, details, user_id=user_id)


@router.get("/schedule", response_model=ScheduleResponse)
async def get_schedule(
    date: str,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    group_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    _parse_date(date)  # validate
    now = datetime.now(MSK)
    current_date_str = now.strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M") if date == current_date_str else None

    if not ctx.groups_roles and not ctx.is_superadmin:
        return ScheduleResponse(date=date, lessons=[])

    target_group_id = (
        group_id
        if group_id
        else (int(next(iter(ctx.groups_roles.keys()))) if ctx.groups_roles else 1)
    )

    # Check permissions for target_group_id
    if not ctx.is_superadmin and str(target_group_id) not in ctx.groups_roles:
        raise HTTPException(status_code=403, detail="Forbidden")

    att_repo = AttendanceRepository(db)
    ovr_repo = OverrideRepository(db)

    overrides = await ovr_repo.get_for_date(target_group_id, date)
    absent_counts = await att_repo.get_absent_count_by_time(target_group_id, date)

    lessons = await build_schedule(
        db, target_group_id, date, overrides, absent_counts, current_time_str
    )
    return ScheduleResponse(date=date, lessons=lessons)


@router.post("/override")
async def update_override(
    data: OverrideUpdateRequest,
    background_tasks: BackgroundTasks,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
    req: dict = Depends(get_request_details),
):
    if not ctx.groups_roles and not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Forbidden")

    target_group_id = (
        data.group_id
        if data.group_id
        else (int(next(iter(ctx.groups_roles.keys()))) if ctx.groups_roles else 1)
    )

    if not ctx.is_superadmin and str(target_group_id) not in ctx.groups_roles:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Only admins can update overrides for this group
    if not ctx.is_superadmin and ctx.groups_roles.get(str(target_group_id)) not in [
        "headman",
        "deputy",
        "curator",
    ]:
        raise HTTPException(status_code=403, detail="Forbidden")

    att_repo = AttendanceRepository(db)
    ovr_repo = OverrideRepository(db)

    await ovr_repo.upsert(
        group_id=target_group_id,
        date=data.date,
        time=data.time,
        new_name=data.new_name,
        new_teacher=data.new_teacher,
        is_canceled=data.is_canceled,
    )

    if data.is_canceled == 1:
        await att_repo.delete_for_lesson(target_group_id, data.date, data.time)

    await db.commit()
    await manager.broadcast({"type": "override", "date": data.date})

    admin_name = get_display_name(ctx.user)
    action = "Отмена пары" if data.is_canceled else "Замена пары"
    background_tasks.add_task(
        _log_schedule_action,
        admin_name,
        action,
        f"{data.date} {data.time} → {data.new_name}",
        ctx.user.id,
    )

    return {"status": "ok"}


@router.get("/base", response_model=list[dict])
async def get_base_schedule(
    group_id: int,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    if not ctx.is_superadmin and str(group_id) not in ctx.groups_roles:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy import select

    from app.models.schedule_new import Lesson, Schedule

    stmt = select(Schedule).where(Schedule.group_id == group_id)
    schedules = (await db.execute(stmt)).scalars().all()

    stmt_lessons = (
        select(Lesson)
        .join(Schedule)
        .where(Schedule.group_id == group_id)
        .order_by(Schedule.day_of_week, Lesson.start_time)
    )
    lessons = (await db.execute(stmt_lessons)).scalars().all()

    res = []
    for day in range(0, 7):
        day_lessons = [
            l
            for l in lessons
            if l.schedule_id in [s.id for s in schedules if s.day_of_week == day]
        ]
        res.append(
            {
                "day_of_week": day,
                "lessons": [
                    {
                        "id": l.id,
                        "lesson_number": l.lesson_number,
                        "name": l.name,
                        "teacher": l.teacher,
                        "classroom": l.classroom,
                        "start_time": l.start_time.strftime("%H:%M"),
                        "end_time": l.end_time.strftime("%H:%M"),
                        "valid_from": l.valid_from.strftime("%Y-%m-%d")
                        if l.valid_from
                        else None,
                        "valid_until": l.valid_until.strftime("%Y-%m-%d")
                        if l.valid_until
                        else None,
                    }
                    for l in day_lessons
                ],
            }
        )
    return res


@router.post("/base/{group_id}/{day_of_week}")
async def create_base_lesson(
    group_id: int,
    day_of_week: int,
    data: dict,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    if not ctx.is_superadmin and str(group_id) not in ctx.groups_roles:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy import select

    from app.models.schedule_new import Lesson, Schedule

    stmt = select(Schedule).where(
        Schedule.group_id == group_id, Schedule.day_of_week == day_of_week
    )
    schedule = (await db.execute(stmt)).scalar_one_or_none()

    if not schedule:
        schedule = Schedule(group_id=group_id, day_of_week=day_of_week)
        db.add(schedule)
        await db.flush()

    lesson = Lesson(
        schedule_id=schedule.id,
        lesson_number=data.get("lesson_number", 1),
        name=data["name"],
        teacher=data.get("teacher"),
        classroom=data.get("classroom"),
        start_time=datetime.strptime(data["start_time"], "%H:%M").time(),
        end_time=datetime.strptime(data["end_time"], "%H:%M").time(),
        valid_from=datetime.strptime(data["valid_from"], "%Y-%m-%d").date()
        if data.get("valid_from")
        else None,
        valid_until=datetime.strptime(data["valid_until"], "%Y-%m-%d").date()
        if data.get("valid_until")
        else None,
    )
    db.add(lesson)
    await db.commit()
    return {"status": "ok", "id": lesson.id}


@router.put("/base/lesson/{lesson_id}")
async def update_base_lesson(
    lesson_id: int,
    data: dict,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    from app.models.schedule_new import Lesson, Schedule

    lesson = await db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    schedule = await db.get(Schedule, lesson.schedule_id)
    if not ctx.is_superadmin and str(schedule.group_id) not in ctx.groups_roles:
        raise HTTPException(status_code=403, detail="Forbidden")

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

    await db.commit()
    return {"status": "ok"}


@router.delete("/base/lesson/{lesson_id}")
async def delete_base_lesson(
    lesson_id: int,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    from app.models.schedule_new import Lesson, Schedule

    lesson = await db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    schedule = await db.get(Schedule, lesson.schedule_id)
    if not ctx.is_superadmin and str(schedule.group_id) not in ctx.groups_roles:
        raise HTTPException(status_code=403, detail="Forbidden")

    await db.delete(lesson)
    await db.commit()
    return {"status": "ok"}
