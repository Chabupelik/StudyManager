from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import DbSession, async_session_maker
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.override_repo import OverrideRepository
from app.repositories.user_repo import UserRepository
from app.schemas.attendance import AttendanceUpdateRequest, LessonDetailsResponse
from app.services.audit_service import log_action
from app.services.schedule_service import (
    compute_active_times,
    get_base_times_for_date,
    get_subject_at,
)
from app.services.user_service import AuthUser, get_display_name
from app.websocket.manager import manager


def _parse_date(date: str) -> datetime:
    try:
        return datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {date!r}. Expected YYYY-MM-DD.",
        )


async def _log_attendance_action(
    admin_name: str, action_type: str, details: str, user_id: int
) -> None:
    async with async_session_maker() as session:
        await log_action(session, admin_name, action_type, details, user_id=user_id)


class AttendanceService:
    def __init__(
        self,
        session: AsyncSession,
        att_repo: AttendanceRepository,
        ovr_repo: OverrideRepository,
        user_repo: UserRepository,
    ) -> None:
        self.session = session
        self.att_repo = att_repo
        self.ovr_repo = ovr_repo
        self.user_repo = user_repo

    async def get_lesson_details(
        self,
        group_id: int,
        date: str,
        time: str,
        user: AuthUser,
    ) -> LessonDetailsResponse:
        _parse_date(date)

        if not user.is_superadmin and str(group_id) not in (user.groups_roles or {}):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: No access to this group",
            )

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
        background_tasks: BackgroundTasks,
    ) -> dict:
        _parse_date(data.date)

        group_id = data.group_id
        if not user.is_superadmin and str(group_id) not in (user.groups_roles or {}):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

        await self.att_repo.upsert(
            group_id=group_id,
            date=data.date,
            time=data.time,
            user_id=data.student_id,
            status=data.status,
            reason=data.reason or "",
        )

        lesson_name = "Пара"
        overrides = await self.ovr_repo.get_for_date(group_id, data.date)
        ovr_map = {o.time: o for o in overrides}
        if data.time in ovr_map and ovr_map[data.time].new_name:
            lesson_name = ovr_map[data.time].new_name
        else:
            weekday = datetime.strptime(data.date, "%Y-%m-%d").weekday()
            name, _ = await get_subject_at(
                self.session, group_id, data.date, data.time, weekday, {}
            )
            if name:
                lesson_name = name

        await self.session.commit()

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

        admin_name = get_display_name(user)
        stat_str = (
            "Н" if data.status == 1 else "У" if data.status == 2 else "Присутствует"
        )
        user_obj = await self.user_repo.get_by_id(data.student_id)
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
            user.id,
        )
        return {"status": "ok"}

    async def update_attendance_day(
        self,
        data: AttendanceUpdateRequest,
        user: AuthUser,
        background_tasks: BackgroundTasks,
    ) -> dict:
        _parse_date(data.date)

        group_id = data.group_id
        if not user.is_superadmin and str(group_id) not in (user.groups_roles or {}):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

        overrides = await self.ovr_repo.get_for_date(group_id, data.date)
        base_times = await get_base_times_for_date(self.session, group_id, data.date)
        active_times = compute_active_times(base_times, overrides)

        for t in active_times:
            await self.att_repo.upsert(
                group_id=group_id,
                date=data.date,
                time=t,
                user_id=data.student_id,
                status=data.status,
                reason=data.reason or "",
            )

        await self.session.commit()

        await manager.broadcast(
            {
                "type": "update_day",
                "date": data.date,
                "student_id": data.student_id,
            }
        )

        admin_name = get_display_name(user)
        user_obj = await self.user_repo.get_by_id(data.student_id)
        student_name = user_obj.full_name if user_obj else f"Студент {data.student_id}"
        stat_str = (
            "Н" if data.status == 1 else "У" if data.status == 2 else "Присутствует"
        )
        background_tasks.add_task(
            _log_attendance_action,
            admin_name,
            "Отметка на весь день",
            f"Студент {student_name} ({data.date}) → {stat_str}",
            user.id,
        )
        return {"status": "ok"}


def get_attendance_service(db: DbSession) -> AttendanceService:
    return AttendanceService(
        session=db,
        att_repo=AttendanceRepository(db),
        ovr_repo=OverrideRepository(db),
        user_repo=UserRepository(db),
    )


AttendanceSrv = Annotated[AttendanceService, Depends(get_attendance_service)]
