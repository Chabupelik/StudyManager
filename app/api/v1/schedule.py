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
