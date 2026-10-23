from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.database import DbSession
from app.integrations import telegram, vk
from app.models.audit import ActionLog
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.duty_repo import DutyRepository
from app.repositories.group_repo import GroupRepository
from app.repositories.override_repo import OverrideRepository
from app.repositories.user_repo import UserRepository
from app.schemas.duty import DutiesResponse, DutyAssignRequest
from app.services.schedule_service import (
    MSK,
    compute_active_times,
    get_base_times_for_date,
)
from app.services.user_service import AuthUser, get_display_name
from app.services.websocket_service import WebSocketService

logger = logging.getLogger("studymanager_api")


class DutyService:
    def __init__(
        self,
        session: AsyncSession,
        duty_repo: DutyRepository,
        att_repo: AttendanceRepository,
        ovr_repo: OverrideRepository,
        user_repo: UserRepository,
        group_repo: GroupRepository,
        audit_repo: AuditRepository,
        settings: Settings,
    ) -> None:
        self.session = session
        self.duty_repo = duty_repo
        self.att_repo = att_repo
        self.ovr_repo = ovr_repo
        self.user_repo = user_repo
        self.group_repo = group_repo
        self.audit_repo = audit_repo
        self.settings = settings

    def _check_group_access(self, group_id: int, user: AuthUser) -> None:
        if not user.is_superadmin and str(group_id) not in (user.groups_roles or {}):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

    def _find_current_lesson_time(
        self, sorted_times: list[str], current_time_str: str
    ) -> str | None:
        for t in sorted_times:
            try:
                start_h, start_m = map(int, t.split(":"))
                end_t = (
                    datetime(1, 1, 1, start_h, start_m) + timedelta(minutes=90)
                ).strftime("%H:%M")
                if t <= current_time_str < end_t:
                    return t
            except ValueError:
                continue

        past = [t for t in sorted_times if t <= current_time_str]
        return past[-1] if past else None

    async def _log_action(
        self, admin_name: str, action_type: str, details: str, user_id: int
    ) -> ActionLog | None:
        if user_id == self.settings.developer_id:
            return None
        return await self.audit_repo.log_action(admin_name, action_type, details)

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

        self._check_group_access(group_id, user)

        duties_map = await self.duty_repo.get_duties_map(group_id)
        overrides = await self.ovr_repo.get_for_date(group_id, date_str)
        base_times = await get_base_times_for_date(self.session, group_id, date_str)
        active_times = compute_active_times(base_times, overrides)
        sorted_times = sorted(active_times)

        target_time = self._find_current_lesson_time(sorted_times, current_time_str)

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

        result = [
            {
                "id": u.id,
                "name": u.full_name,
                "tg_id": u.tg_user_id or 0,
                "date": duties_map.get(u.id),
                "is_absent_now": u.id in absent_ids,
            }
            for u in users
        ]

        result.sort(key=lambda x: (x["date"] is not None, x["date"] or ""))
        return DutiesResponse(duties=result)

    async def assign_duties(
        self,
        data: DutyAssignRequest,
        user: AuthUser,
        background_tasks: BackgroundTasks,
    ) -> dict:
        self._check_group_access(data.group_id, user)

        current_duties = await self.duty_repo.get_duties_map(data.group_id)
        undo_id = str(uuid.uuid4())[:8]

        undo_data = [
            {
                "id": user_id,
                "group_id": data.group_id,
                "date": current_duties.get(user_id),
            }
            for user_id in data.student_ids
        ]
        await self.duty_repo.save_undo(undo_id, undo_data)

        records = [
            {
                "group_id": data.group_id,
                "user_id": user_id,
                "date": data.date,
            }
            for user_id in data.student_ids
        ]
        await self.duty_repo.upsert_many(records)

        users = await self.user_repo.get_by_ids(data.student_ids)
        user_map = {u.id: u for u in users}
        assigned_names = [
            user_map[uid].full_name
            if uid in user_map and user_map[uid].full_name
            else f"Пользователь {uid}"
            for uid in data.student_ids
        ]

        admin_name = get_display_name(user)
        short_names = ", ".join(n.split()[0] for n in assigned_names)
        log_entry = await self._log_action(
            admin_name,
            "Назначение дежурных",
            f"Дата: {data.date}. Дежурят: {short_names}",
            user.id,
        )

        await self.session.commit()

        try:
            await WebSocketService.broadcast_duties()
            if log_entry:
                created_at_val = (
                    float(log_entry.created_at.timestamp())
                    if hasattr(log_entry.created_at, "timestamp")
                    else float(log_entry.created_at)
                )
                await WebSocketService.broadcast_new_log(
                    {
                        "id": log_entry.id,
                        "admin_name": log_entry.admin_name,
                        "action_type": log_entry.action_type,
                        "details": log_entry.details,
                        "created_at": created_at_val,
                    }
                )
        except Exception as e:
            logger.warning("Failed to broadcast duty events: %s", e)

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

        group_obj = await self.group_repo.get_by_id(data.group_id)
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

        return {"status": "ok"}


def get_duty_service(db: DbSession) -> DutyService:
    return DutyService(
        session=db,
        duty_repo=DutyRepository(db),
        att_repo=AttendanceRepository(db),
        ovr_repo=OverrideRepository(db),
        user_repo=UserRepository(db),
        group_repo=GroupRepository(db),
        audit_repo=AuditRepository(db),
        settings=get_settings(),
    )


DutySrv = Annotated[DutyService, Depends(get_duty_service)]
