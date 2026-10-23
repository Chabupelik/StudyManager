from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.database import DbSession, async_session_maker
from app.integrations import telegram, vk
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.duty_repo import DutyRepository
from app.repositories.group_repo import GroupRepository
from app.repositories.override_repo import OverrideRepository
from app.repositories.user_repo import UserRepository
from app.schemas.duty import DutiesResponse, DutyAssignRequest
from app.services.audit_service import log_action
from app.services.schedule_service import (
    MSK,
    compute_active_times,
    get_base_times_for_date,
)
from app.services.user_service import AuthUser, get_display_name
from app.websocket.manager import manager


async def _log_duties_action(
    admin_name: str, action_type: str, details: str, user_id: int
) -> None:
    async with async_session_maker() as session:
        await log_action(session, admin_name, action_type, details, user_id=user_id)


class DutyService:
    def __init__(
        self,
        session: AsyncSession,
        duty_repo: DutyRepository,
        att_repo: AttendanceRepository,
        ovr_repo: OverrideRepository,
        user_repo: UserRepository,
        group_repo: GroupRepository,
        settings: Settings,
    ) -> None:
        self.session = session
        self.duty_repo = duty_repo
        self.att_repo = att_repo
        self.ovr_repo = ovr_repo
        self.user_repo = user_repo
        self.group_repo = group_repo
        self.settings = settings

    async def get_duties(
        self,
        user: AuthUser,
        group_id: int | None = None,
    ) -> DutiesResponse:
        now = datetime.now(MSK)
        date_str = now.strftime("%Y-%m-%d")
        current_time_str = now.strftime("%H:%M")

        if not user.groups_roles and not user.is_superadmin:
            return DutiesResponse(duties=[])

        if group_id is None:
            group_id = (
                int(next(iter(user.groups_roles.keys()))) if user.groups_roles else 1
            )

        if not user.is_superadmin and str(group_id) not in user.groups_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

        duties_map = await self.duty_repo.get_duties_map(group_id)
        overrides = await self.ovr_repo.get_for_date(group_id, date_str)
        base_times = await get_base_times_for_date(self.session, group_id, date_str)
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
            for r in await self.att_repo.get_for_lesson(
                group_id, date_str, target_time
            ):
                if r.status > 0:
                    absent_ids.add(r.user_id)

        users = await self.user_repo.get_group_students(
            group_id, exclude_duty_exempt=True
        )

        result = []
        for u in users:
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

    async def assign_duties(
        self,
        data: DutyAssignRequest,
        user: AuthUser,
        background_tasks: BackgroundTasks,
    ) -> dict:
        group_id = data.group_id
        if not user.is_superadmin and str(group_id) not in (user.groups_roles or {}):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

        current_duties = await self.duty_repo.get_duties_map(group_id)
        undo_data = []
        assigned_names = []
        undo_id = str(uuid.uuid4())[:8]

        for user_id in data.student_ids:
            undo_data.append(
                {
                    "id": user_id,
                    "group_id": group_id,
                    "date": current_duties.get(user_id),
                }
            )
            await self.duty_repo.upsert(group_id, user_id, data.date)
            user_obj = await self.user_repo.get_by_id(user_id)
            name = user_obj.full_name if user_obj else f"Пользователь {user_id}"
            assigned_names.append(name)

        await self.duty_repo.save_undo(undo_id, undo_data)
        await self.session.commit()

        await manager.broadcast({"type": "update_duties"})

        admin_name = get_display_name(user)
        date_nice = datetime.strptime(data.date, "%Y-%m-%d").strftime("%d.%m.%Y")
        tg_text = (
            f"🔔 <b>Назначены дежурные (через сайт)!</b>\n"
            f"📅 Дата: <code>{date_nice}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        for name in assigned_names:
            tg_text += f"✅ <b>{name}</b>\n"
        tg_text += (
            f'\n👤 <b>Назначил:</b> <a href="tg://user?id={user.id}">{admin_name}</a>'
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "↩️ Отменить назначение",
                        "callback_data": f"web_undo:{undo_id}",
                    }
                ]
            ]
        }

        group_obj = await self.group_repo.get_by_id(group_id)
        tg_chat_id = (
            group_obj.tg_chat_id
            if group_obj and group_obj.tg_chat_id
            else self.settings.group_id
        )
        vk_peer_id = (
            group_obj.vk_peer_id
            if group_obj and group_obj.vk_peer_id
            else self.settings.vk_chat_peer_id
        )

        background_tasks.add_task(
            telegram.send_message, tg_chat_id, tg_text, "HTML", keyboard
        )
        background_tasks.add_task(vk.send_message, tg_text, vk_peer_id)

        short_names = ", ".join(n.split()[0] for n in assigned_names)
        background_tasks.add_task(
            _log_duties_action,
            admin_name,
            "Назначение дежурных",
            f"Дата: {data.date}. Дежурят: {short_names}",
            user.id,
        )
        return {"status": "ok"}


def get_duty_service(db: DbSession) -> DutyService:
    return DutyService(
        session=db,
        duty_repo=DutyRepository(db),
        att_repo=AttendanceRepository(db),
        ovr_repo=OverrideRepository(db),
        user_repo=UserRepository(db),
        group_repo=GroupRepository(db),
        settings=get_settings(),
    )


DutySrv = Annotated[DutyService, Depends(get_duty_service)]
