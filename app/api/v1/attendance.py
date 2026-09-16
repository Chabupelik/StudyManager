from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    UserPermissionContext,
    get_current_user_context,
)
from app.db.database import async_session_maker, get_db
from app.models.group_member import GroupMember, MemberRole
from app.models.user import User
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.override_repo import OverrideRepository
from app.schemas.attendance import AttendanceUpdateRequest, LessonDetailsResponse
from app.services.audit_service import log_action
from app.services.schedule_service import (
    compute_active_times,
    get_base_times_for_date,
)
from app.services.user_service import get_display_name
from app.websocket.manager import manager

router = APIRouter(tags=["attendance"])


def _parse_date(date: str) -> datetime:
    """Validate and parse a YYYY-MM-DD date string. Raises 400 on invalid format."""
    try:
        return datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: {date!r}. Expected YYYY-MM-DD.",
        )


@router.get("/lesson_details", response_model=LessonDetailsResponse)
async def get_lesson_details(
    date: str,
    time: str,
    group_id: int,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    _parse_date(date)  # validate

    if not ctx.is_superadmin and group_id not in (ctx.groups_roles or {}):
        raise HTTPException(
            status_code=403, detail="Forbidden: No access to this group"
        )

    att_repo = AttendanceRepository(db)
    ovr_repo = OverrideRepository(db)

    current_att = {
        r.user_id: r for r in await att_repo.get_for_lesson(group_id, date, time)
    }
    all_day_att = await att_repo.get_for_date(group_id, date)

    overrides = await ovr_repo.get_for_date(group_id, date)
    base_times = await get_base_times_for_date(db, group_id, date)
    active_times = compute_active_times(base_times, overrides)

    student_day_map: dict[int, dict[str, int]] = {}
    for r in all_day_att:
        if r.user_id not in student_day_map:
            student_day_map[r.user_id] = {}
        student_day_map[r.user_id][r.time] = r.status

    stmt = (
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(
            GroupMember.group_id == group_id,
            GroupMember.role.in_(
                [MemberRole.student, MemberRole.headman, MemberRole.deputy]
            ),
        )
        .order_by(User.full_name)
    )
    users = (await db.execute(stmt)).scalars().all()

    result = []
    for u in users:
        s_id = u.id
        curr = current_att.get(s_id)
        curr_status = curr.status if curr else 0
        curr_reason = curr.reason if curr else ""

        is_all_day = False
        if curr_status > 0 and active_times:
            marks = student_day_map.get(s_id, {})
            matches = sum(1 for t in active_times if marks.get(t, 0) == curr_status)
            is_all_day = matches == len(active_times)

        result.append(
            {
                "id": s_id,
                "tg_id": u.tg_user_id or 0,
                "name": u.full_name,
                "status": curr_status,
                "reason": curr_reason,
                "is_all_day": is_all_day,
            }
        )

    return LessonDetailsResponse(students=result)


async def _log_attendance_action(
    admin_name: str, action_type: str, details: str, user_id: int
) -> None:
    async with async_session_maker() as session:
        await log_action(session, admin_name, action_type, details, user_id=user_id)


@router.post("/attendance")
async def update_attendance(
    data: AttendanceUpdateRequest,
    background_tasks: BackgroundTasks,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    _parse_date(data.date)  # validate

    group_id = data.group_id
    if not ctx.is_superadmin and group_id not in (ctx.groups_roles or {}):
        raise HTTPException(status_code=403, detail="Forbidden")

    att_repo = AttendanceRepository(db)
    ovr_repo = OverrideRepository(db)

    await att_repo.upsert(
        group_id=group_id,
        date=data.date,
        time=data.time,
        user_id=data.student_id,  # student_id from frontend is now user_id
        status=data.status,
        reason=data.reason or "",
    )

    lesson_name = "Пара"
    overrides = await ovr_repo.get_for_date(group_id, data.date)
    ovr_map = {o.time: o for o in overrides}
    if data.time in ovr_map and ovr_map[data.time].new_name:
        lesson_name = ovr_map[data.time].new_name
    else:
        weekday = datetime.strptime(data.date, "%Y-%m-%d").weekday()
        from app.services.schedule_service import get_subject_at

        name, _ = await get_subject_at(db, group_id, data.date, data.time, weekday, {})
        if name:
            lesson_name = name

    await db.commit()

    await manager.broadcast(
        {
            "type": "update_attendance",
            "date": data.date,
            "time": data.time,
            "student_id": data.student_id,
            "status": data.status,
            "reason": data.reason,
        }
    )

    admin_name = get_display_name(ctx.user)
    stat_str = "Н" if data.status == 1 else "У" if data.status == 2 else "Присутствует"
    user_obj = await db.get(User, data.student_id)
    student_name = user_obj.full_name if user_obj else f"Студент {data.student_id}"
    fmt_date = datetime.strptime(data.date, "%Y-%m-%d").strftime("%d.%m")
    log_details = (
        f"{fmt_date} | {data.time} | {lesson_name}\n{student_name} ➔ {stat_str}"
    )

    background_tasks.add_task(
        _log_attendance_action,
        admin_name,
        "Изменение отметки",
        log_details,
        ctx.user.id,
    )
    return {"status": "ok"}


@router.post("/attendance/day")
async def update_attendance_day(
    data: AttendanceUpdateRequest,
    background_tasks: BackgroundTasks,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    _parse_date(data.date)  # validate

    group_id = data.group_id
    if not ctx.is_superadmin and group_id not in (ctx.groups_roles or {}):
        raise HTTPException(status_code=403, detail="Forbidden")

    att_repo = AttendanceRepository(db)
    ovr_repo = OverrideRepository(db)

    overrides = await ovr_repo.get_for_date(group_id, data.date)
    base_times = await get_base_times_for_date(db, group_id, data.date)
    active_times = compute_active_times(base_times, overrides)

    for t in active_times:
        await att_repo.upsert(
            group_id=group_id,
            date=data.date,
            time=t,
            user_id=data.student_id,
            status=data.status,
            reason=data.reason or "",
        )

    await db.commit()

    await manager.broadcast(
        {
            "type": "update_day",
            "date": data.date,
            "student_id": data.student_id,
        }
    )

    admin_name = get_display_name(ctx.user)
    user_obj = await db.get(User, data.student_id)
    student_name = user_obj.full_name if user_obj else f"Студент {data.student_id}"
    stat_str = "Н" if data.status == 1 else "У" if data.status == 2 else "Присутствует"
    background_tasks.add_task(
        _log_attendance_action,
        admin_name,
        "Отметка на весь день",
        f"Студент {student_name} ({data.date}) → {stat_str}",
        ctx.user.id,
    )
    return {"status": "ok"}
