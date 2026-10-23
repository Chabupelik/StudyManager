from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.database import DbSession
from app.models.audit import ActionLog
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.override_repo import OverrideRepository
from app.repositories.user_repo import UserRepository
from app.schemas.attendance import AttendanceUpdateRequest, LessonDetailsResponse
from app.services.schedule_service import (
    compute_active_times,
    get_base_times_for_date,
    get_subject_at,
)
from app.services.user_service import AuthUser, get_display_name
from app.services.websocket_service import WebSocketService

logger = logging.getLogger("studymanager_api")


def _parse_date(date: str) -> datetime:
    try:
        return datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {date!r}. Expected YYYY-MM-DD.",
        )


def _format_status(status_code: int) -> str:
    if status_code == 1:
        return "Н"
    if status_code == 2:
        return "У"
    return "Присутствует"


class AttendanceService:
    def __init__(
        self,
        session: AsyncSession,
        att_repo: AttendanceRepository,
        ovr_repo: OverrideRepository,
        user_repo: UserRepository,
        audit_repo: AuditRepository,
    ) -> None:
        self.session = session
        self.att_repo = att_repo
        self.ovr_repo = ovr_repo
        self.user_repo = user_repo
        self.audit_repo = audit_repo

    def _check_group_access(self, group_id: int, user: AuthUser) -> None:
        if not user.is_superadmin and str(group_id) not in (user.groups_roles or {}):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: No access to this group",
            )

    async def _get_lesson_name(
        self, group_id: int, date: str, time: str, weekday: int
    ) -> str:
        overrides = await self.ovr_repo.get_for_date(group_id, date)
        ovr_map = {o.time: o for o in overrides}
        if time in ovr_map and ovr_map[time].new_name:
            return ovr_map[time].new_name
        name, _ = await get_subject_at(self.session, group_id, date, time, weekday, {})
        return name or "Пара"

    async def _log_action(
        self, admin_name: str, action_type: str, details: str, user_id: int
    ) -> ActionLog | None:
        if user_id == get_settings().developer_id:
            return None
        return await self.audit_repo.log_action(admin_name, action_type, details)

    async def get_lesson_details(
        self,
        group_id: int,
        date: str,
        time: str,
        user: AuthUser,
    ) -> LessonDetailsResponse:
        _parse_date(date)
        self._check_group_access(group_id, user)

        current_att = {
            r.user_id: r
            for r in await self.att_repo.get_for_lesson(group_id, date, time)
        }
        all_day_att = await self.att_repo.get_for_date(group_id, date)

        overrides = await self.ovr_repo.get_for_date(group_id, date)
        base_times = await get_base_times_for_date(self.session, group_id, date)
        active_times = compute_active_times(base_times, overrides)

        student_day_map: dict[int, dict[str, int]] = {}
        for r in all_day_att:
            if r.user_id not in student_day_map:
                student_day_map[r.user_id] = {}
            student_day_map[r.user_id][r.time] = r.status

        users = await self.user_repo.get_group_students(group_id)

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

    async def update_attendance(
        self,
        data: AttendanceUpdateRequest,
        user: AuthUser,
    ) -> dict:
        dt = _parse_date(data.date)
        self._check_group_access(data.group_id, user)

        await self.att_repo.upsert(
            group_id=data.group_id,
            date=data.date,
            time=data.time,
            user_id=data.student_id,
            status=data.status,
            reason=data.reason or "",
        )

        lesson_name = await self._get_lesson_name(
            data.group_id, data.date, data.time, dt.isoweekday()
        )
        admin_name = get_display_name(user)
        stat_str = _format_status(data.status)
        user_obj = await self.user_repo.get_by_id(data.student_id)
        student_name = user_obj.full_name if user_obj else f"Студент {data.student_id}"
        fmt_date = dt.strftime("%d.%m")
        log_details = (
            f"{fmt_date} | {data.time} | {lesson_name}\n{student_name} ➔ {stat_str}"
        )

        log_entry = await self._log_action(
            admin_name, "Изменение отметки", log_details, user.id
        )
        await self.session.commit()

        try:
            await WebSocketService.broadcast_attendance(
                date=data.date,
                time=data.time,
                student_id=data.student_id,
                status=data.status,
                reason=data.reason,
            )
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
            logger.warning("Failed to broadcast attendance update: %s", e)

        return {"status": "ok"}

    async def update_attendance_day(
        self,
        data: AttendanceUpdateRequest,
        user: AuthUser,
    ) -> dict:
        _parse_date(data.date)
        self._check_group_access(data.group_id, user)

        overrides = await self.ovr_repo.get_for_date(data.group_id, data.date)
        base_times = await get_base_times_for_date(
            self.session, data.group_id, data.date
        )
        active_times = compute_active_times(base_times, overrides)

        if not active_times:
            return {"status": "ok", "message": "На этот день нет занятий"}

        records = [
            {
                "group_id": data.group_id,
                "date": data.date,
                "time": t,
                "user_id": data.student_id,
                "status": data.status,
                "reason": data.reason or "",
            }
            for t in active_times
        ]
        await self.att_repo.upsert_many(records)

        admin_name = get_display_name(user)
        user_obj = await self.user_repo.get_by_id(data.student_id)
        student_name = user_obj.full_name if user_obj else f"Студент {data.student_id}"
        stat_str = _format_status(data.status)
        log_entry = await self._log_action(
            admin_name,
            "Отметка на весь день",
            f"Студент {student_name} ({data.date}) → {stat_str}",
            user.id,
        )
        await self.session.commit()

        try:
            await WebSocketService.broadcast_day_attendance(
                date=data.date,
                student_id=data.student_id,
            )
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
            logger.warning("Failed to broadcast day attendance update: %s", e)

        return {"status": "ok"}


def get_attendance_service(db: DbSession) -> AttendanceService:
    return AttendanceService(
        session=db,
        att_repo=AttendanceRepository(db),
        ovr_repo=OverrideRepository(db),
        user_repo=UserRepository(db),
        audit_repo=AuditRepository(db),
    )


AttendanceSrv = Annotated[AttendanceService, Depends(get_attendance_service)]
