from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    UserPermissionContext,
    get_current_user_context,
)
from app.core.config import get_settings
from app.data.students_data import EXCLUDED_DUTY_STUDENT_IDS
from app.db.database import async_session_maker, get_db
from app.integrations import telegram, vk
from app.models.group_member import GroupMember, MemberRole
from app.models.user import User
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.duty_repo import DutyRepository
from app.repositories.override_repo import OverrideRepository
from app.schemas.duty import DutiesResponse, DutyAssignRequest
from app.services.audit_service import log_action
from app.services.schedule_service import (
    MSK,
    compute_active_times,
    get_base_times_for_date,
)
from app.services.user_service import get_display_name
from app.websocket.manager import manager

router = APIRouter(tags=["duties"])


async def _log_duties_action(
    admin_name: str, action_type: str, details: str, user_id: int
) -> None:
    async with async_session_maker() as session:
        await log_action(session, admin_name, action_type, details, user_id=user_id)


@router.get("/duties", response_model=DutiesResponse)
async def get_duties(
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
    group_id: int | None = None,
):
    now = datetime.now(MSK)
    date_str = now.strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M")

    if not ctx.groups_roles and not ctx.is_superadmin:
        return DutiesResponse(duties=[])

    if group_id is None:
        group_id = int(next(iter(ctx.groups_roles.keys()))) if ctx.groups_roles else 1

    if not ctx.is_superadmin and str(group_id) not in ctx.groups_roles:
        raise HTTPException(status_code=403, detail="Forbidden")

    duty_repo = DutyRepository(db)
    att_repo = AttendanceRepository(db)
    ovr_repo = OverrideRepository(db)

    duties_map = await duty_repo.get_all(group_id)
    overrides = await ovr_repo.get_for_date(group_id, date_str)
    base_times = await get_base_times_for_date(db, group_id, date_str)
    active_times = compute_active_times(base_times, overrides)
    sorted_times = sorted(active_times)

    target_time: str | None = None
    for t in sorted_times:
        try:
            start_h, start_m = map(int, t.split(":"))
            end_t = (
                datetime(1, 1, 1, start_h, start_m) + timedelta(minutes=90)
            ).strftime("%H:%M")
            if t <= current_time_str < end_t:
                target_time = t
                break
        except ValueError:
            continue

    if not target_time and sorted_times:
        past = [t for t in sorted_times if t <= current_time_str]
        if past:
            target_time = past[-1]

    absent_ids: set[int] = set()
    if target_time:
        for r in await att_repo.get_for_lesson(group_id, date_str, target_time):
            if r.status > 0:
                absent_ids.add(r.user_id)

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
        # Temporary compat for EXCLUDED_DUTY_STUDENT_IDS (by old ID)
        if u.id in EXCLUDED_DUTY_STUDENT_IDS:
            continue
        result.append(
            {
                "id": u.id,
                "name": u.full_name,
                "tg_id": u.tg_user_id or 0,
                "date": duties_map.get(u.id),
                "is_absent_now": u.id in absent_ids,
            }
        )

    result.sort(key=lambda x: (x["date"] is not None, x["date"] or ""))
    return DutiesResponse(duties=result)


@router.post("/duties/assign")
async def assign_duties(
    data: DutyAssignRequest,
    background_tasks: BackgroundTasks,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    duty_repo = DutyRepository(db)

    group_id = data.group_id
    if not ctx.is_superadmin and str(group_id) not in (ctx.groups_roles or {}):
        raise HTTPException(status_code=403, detail="Forbidden")

    current_duties = await duty_repo.get_all(group_id)
    undo_data = []
    assigned_names = []
    undo_id = str(uuid.uuid4())[:8]

    for user_id in data.student_ids:
        undo_data.append({"id": user_id, "date": current_duties.get(user_id)})
        await duty_repo.upsert(group_id, user_id, data.date)
        user_obj = await db.get(User, user_id)
        name = user_obj.full_name if user_obj else f"Пользователь {user_id}"
        assigned_names.append(name)

    await duty_repo.save_undo(undo_id, undo_data)
    await db.commit()

    await manager.broadcast({"type": "update_duties"})

    admin_name = get_display_name(ctx.user)
    date_nice = datetime.strptime(data.date, "%Y-%m-%d").strftime("%d.%m.%Y")
    tg_text = (
        f"🔔 <b>Назначены дежурные (через сайт)!</b>\n"
        f"📅 Дата: <code>{date_nice}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
    )
    for name in assigned_names:
        tg_text += f"✅ <b>{name}</b>\n"
    tg_text += (
        f'\n👤 <b>Назначил:</b> <a href="tg://user?id={ctx.user.id}">{admin_name}</a>'
    )

    keyboard = {
        "inline_keyboard": [
            [{"text": "↩️ Отменить назначение", "callback_data": f"web_undo:{undo_id}"}]
        ]
    }

    background_tasks.add_task(
        telegram.send_message, settings.group_id, tg_text, "HTML", keyboard
    )
    background_tasks.add_task(vk.send_message, tg_text)

    short_names = ", ".join(n.split()[0] for n in assigned_names)
    background_tasks.add_task(
        _log_duties_action,
        admin_name,
        "Назначение дежурных",
        f"Дата: {data.date}. Дежурят: {short_names}",
        ctx.user.id,
    )
    return {"status": "ok"}


@router.post("/internal/broadcast_duties")
async def broadcast_duties(
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
):
    await manager.broadcast({"type": "update_duties"})
    return {"status": "ok"}
