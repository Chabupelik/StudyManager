from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import DbSession, async_session_maker
from app.db.redis_client import RedisClient
from app.models.override import Override
from app.models.schedule_new import Lesson
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.override_repo import OverrideRepository
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.schedule import (
    BaseLessonCreateRequest,
    BaseLessonUpdateRequest,
    OverrideUpdateRequest,
    ScheduleResponse,
)
from app.services.audit_service import log_action
from app.services.user_service import AuthUser, get_display_name
from app.services.websocket_service import WebSocketService

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")
LESSON_DURATION_MINUTES = 90


def _parse_date(date: str) -> datetime:
    try:
        return datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {date!r}",
        )


async def _log_schedule_action(
    admin_name: str, action_type: str, details: str, user_id: int
) -> None:
    async with async_session_maker() as session:
        await log_action(session, admin_name, action_type, details, user_id=user_id)


async def get_base_times_for_date(
    session: AsyncSession, group_id: int, date_str: str
) -> set[str]:
    return await ScheduleRepository(session).get_base_times_for_date(group_id, date_str)


async def get_base_lessons_for_date(
    session: AsyncSession, group_id: int, date_str: str
) -> list[dict]:
    lessons = await ScheduleRepository(session).get_base_lessons_for_date(
        group_id, date_str
    )
    return [
        {
            "time": l.start_time.strftime("%H:%M"),
            "name": l.name,
            "teacher": l.teacher,
            "classroom": l.classroom,
        }
        for l in lessons
    ]


def compute_active_times(base_times: set[str], overrides: list[Override]) -> set[str]:
    canceled = {o.time for o in overrides if o.is_canceled}
    added = {
        o.time for o in overrides if not o.is_canceled and o.time not in base_times
    }
    return (base_times - canceled) | added


async def build_schedule(
    session: AsyncSession,
    group_id: int,
    date_str: str,
    overrides: list[Override],
    absent_counts: dict[str, int],
    current_time_str: str | None = None,
) -> list[dict]:
    base_lessons = await get_base_lessons_for_date(session, group_id, date_str)
    override_map: dict[str, Override] = {o.time: o for o in overrides}

    temp: list[dict] = []
    processed_times: set[str] = set()

    for lesson in base_lessons:
        t = lesson["time"]
        processed_times.add(t)
        ovr = override_map.get(t)
        temp.append(
            {
                "time": t,
                "name": (ovr.new_name if ovr and ovr.new_name else lesson["name"]),
                "teacher": (
                    ovr.new_teacher
                    if ovr and ovr.new_teacher
                    else lesson.get("teacher") or "Не назначен"
                ),
                "classroom": lesson.get("classroom"),
                "canceled": bool(ovr and ovr.is_canceled),
                "absent_count": absent_counts.get(t, 0),
            }
        )

    for t, ovr in override_map.items():
        if t not in processed_times:
            temp.append(
                {
                    "time": t,
                    "name": ovr.new_name or "Без названия",
                    "teacher": ovr.new_teacher or "Не назначен",
                    "classroom": None,
                    "canceled": bool(ovr.is_canceled),
                    "absent_count": absent_counts.get(t, 0),
                }
            )

    temp.sort(key=lambda x: x["time"].zfill(5))

    current_id: str | None = None
    if current_time_str:
        for lesson in temp:
            if lesson["canceled"]:
                continue
            t = lesson["time"]
            try:
                start_h, start_m = map(int, t.split(":"))
                end_t = (
                    datetime(1, 1, 1, start_h, start_m)
                    + timedelta(minutes=LESSON_DURATION_MINUTES)
                ).strftime("%H:%M")
                if t <= current_time_str < end_t:
                    current_id = t
                    break
            except ValueError:
                continue

    for lesson in temp:
        lesson["is_current"] = lesson["time"] == current_id

    return temp


async def get_subject_at(
    session: AsyncSession,
    group_id: int,
    date_str: str,
    time_str: str,
    weekday: int,
    override_map: dict[tuple[str, str], dict],
) -> tuple[str | None, str | None]:
    ovr = override_map.get((date_str, time_str))
    if ovr and ovr["canceled"]:
        return None, None

    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    repo = ScheduleRepository(session)

    if ovr and ovr["name"]:
        teacher = await repo.get_teacher_for_lesson_name(group_id, ovr["name"])
        return ovr["name"], teacher or "Замена"

    time_obj = datetime.strptime(time_str, "%H:%M").time()
    match = await repo.get_lesson_at_time(group_id, weekday, time_obj, date_obj)
    if match:
        return match.name, match.teacher
    return None, None


class ScheduleService:
    def __init__(
        self,
        session: AsyncSession,
        schedule_repo: ScheduleRepository,
        att_repo: AttendanceRepository,
        ovr_repo: OverrideRepository,
        redis: RedisClient | None = None,
    ) -> None:
        self.session = session
        self.schedule_repo = schedule_repo
        self.att_repo = att_repo
        self.ovr_repo = ovr_repo
        self.redis = redis

    async def _invalidate_base_schedule(self, group_id: int) -> None:
        if self.redis is not None:
            try:
                await self.redis.delete(f"cache:schedule:base:{group_id}")
                await self.redis.delete(f"cache:groups_schedule:full:{group_id}")
            except Exception as e:
                logger.warning(
                    "Redis invalidate base schedule failed for %s: %s", group_id, e
                )

    def _check_can_view(self, group_id: int, user: AuthUser) -> None:
        if not user.is_superadmin and str(group_id) not in user.groups_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

    def _check_can_manage(self, group_id: int, user: AuthUser) -> None:
        if not user.is_admin(group_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

    async def get_schedule(
        self,
        date: str,
        current_user: AuthUser,
        group_id: int | None = None,
    ) -> ScheduleResponse:
        _parse_date(date)
        now = datetime.now(MSK)
        current_date_str = now.strftime("%Y-%m-%d")
        current_time_str = now.strftime("%H:%M") if date == current_date_str else None

        if not current_user.groups_roles and not current_user.is_superadmin:
            return ScheduleResponse(date=date, lessons=[])

        target_group_id = (
            group_id
            if group_id
            else (
                int(next(iter(current_user.groups_roles.keys())))
                if current_user.groups_roles
                else 1
            )
        )

        self._check_can_view(target_group_id, current_user)

        overrides = await self.ovr_repo.get_for_date(target_group_id, date)
        absent_counts = await self.att_repo.get_absent_count_by_time(
            target_group_id, date
        )

        lessons = await build_schedule(
            self.session,
            target_group_id,
            date,
            overrides,
            absent_counts,
            current_time_str,
        )
        return ScheduleResponse(date=date, lessons=lessons)

    async def update_override(
        self,
        data: OverrideUpdateRequest,
        current_user: AuthUser,
        background_tasks: BackgroundTasks,
    ) -> dict:
        if not current_user.groups_roles and not current_user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

        target_group_id = (
            data.group_id
            if data.group_id
            else (
                int(next(iter(current_user.groups_roles.keys())))
                if current_user.groups_roles
                else 1
            )
        )

        self._check_can_manage(target_group_id, current_user)

        await self.ovr_repo.upsert(
            group_id=target_group_id,
            date=data.date,
            time=data.time,
            new_name=data.new_name,
            new_teacher=data.new_teacher,
            is_canceled=data.is_canceled,
        )

        if data.is_canceled == 1:
            await self.att_repo.delete_for_lesson(target_group_id, data.date, data.time)

        await self.session.commit()
        await WebSocketService.broadcast_override(data.date)

        admin_name = get_display_name(current_user)
        action = "Отмена пары" if data.is_canceled else "Замена пары"
        background_tasks.add_task(
            _log_schedule_action,
            admin_name,
            action,
            f"{data.date} {data.time} → {data.new_name}",
            current_user.id,
        )
        return {"status": "ok"}

    async def get_base_schedule(
        self,
        group_id: int,
        current_user: AuthUser,
    ) -> list[dict]:
        self._check_can_view(group_id, current_user)

        cache_key = f"cache:schedule:base:{group_id}"
        if self.redis is not None:
            try:
                cached = await self.redis.get(cache_key)
                if cached is not None:
                    return json.loads(cached)
            except Exception as e:
                logger.warning("Redis get base schedule failed for %s: %s", group_id, e)

        schedules, lessons = await self.schedule_repo.get_base_lessons_with_schedules(
            group_id
        )

        sched_to_day = {s.id: s.day_of_week for s in schedules}
        lessons_by_day: dict[int, list[Lesson]] = {d: [] for d in range(0, 7)}
        for l in lessons:
            day = sched_to_day.get(l.schedule_id)
            if day in lessons_by_day:
                lessons_by_day[day].append(l)

        res = []
        for day in range(0, 7):
            res.append(
                {
                    "group_id": group_id,
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
                            "valid_from": (
                                l.valid_from.strftime("%Y-%m-%d")
                                if l.valid_from
                                else None
                            ),
                            "valid_until": (
                                l.valid_until.strftime("%Y-%m-%d")
                                if l.valid_until
                                else None
                            ),
                        }
                        for l in lessons_by_day[day]
                    ],
                }
            )

        if self.redis is not None:
            try:
                await self.redis.set(cache_key, json.dumps(res), ex=3600)
            except Exception as e:
                logger.warning("Redis set base schedule failed for %s: %s", group_id, e)

        return res

    async def create_base_lesson(
        self,
        group_id: int,
        day_of_week: int,
        body: BaseLessonCreateRequest,
        current_user: AuthUser,
    ) -> dict:
        self._check_can_manage(group_id, current_user)

        schedule = await self.schedule_repo.get_or_create_schedule(
            group_id, day_of_week
        )

        start_time_obj = datetime.strptime(body.start_time, "%H:%M").time()
        end_time_obj = datetime.strptime(body.end_time, "%H:%M").time()
        valid_from_obj = (
            datetime.strptime(body.valid_from, "%Y-%m-%d").date()
            if body.valid_from
            else None
        )
        valid_until_obj = (
            datetime.strptime(body.valid_until, "%Y-%m-%d").date()
            if body.valid_until
            else None
        )

        lesson = await self.schedule_repo.create_lesson(
            schedule_id=schedule.id,
            lesson_number=body.lesson_number,
            name=body.name,
            teacher=body.teacher,
            classroom=body.classroom,
            start_time=start_time_obj,
            end_time=end_time_obj,
            valid_from=valid_from_obj,
            valid_until=valid_until_obj,
        )
        await self.session.commit()
        await self._invalidate_base_schedule(group_id)
        return {"status": "ok", "id": lesson.id}

    async def update_base_lesson(
        self,
        lesson_id: int,
        body: BaseLessonUpdateRequest,
        current_user: AuthUser,
    ) -> dict:
        lesson = await self.schedule_repo.get_lesson_by_id(lesson_id)
        if not lesson:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lesson not found",
            )

        schedule = await self.schedule_repo.get_by_id(lesson.schedule_id)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule not found",
            )
        self._check_can_manage(schedule.group_id, current_user)

        await self.schedule_repo.update_lesson(
            lesson, body.model_dump(exclude_unset=True)
        )
        await self.session.commit()
        await self._invalidate_base_schedule(schedule.group_id)
        return {"status": "ok"}

    async def delete_base_lesson(
        self,
        lesson_id: int,
        current_user: AuthUser,
    ) -> dict:
        lesson = await self.schedule_repo.get_lesson_by_id(lesson_id)
        if not lesson:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lesson not found",
            )

        schedule = await self.schedule_repo.get_by_id(lesson.schedule_id)
        if not schedule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule not found",
            )
        self._check_can_manage(schedule.group_id, current_user)

        await self.schedule_repo.delete_lesson(lesson)
        await self.session.commit()
        await self._invalidate_base_schedule(schedule.group_id)
        return {"status": "ok"}


def get_schedule_service(db: DbSession, redis: RedisClient) -> ScheduleService:
    return ScheduleService(
        session=db,
        schedule_repo=ScheduleRepository(db),
        att_repo=AttendanceRepository(db),
        ovr_repo=OverrideRepository(db),
        redis=redis,
    )


ScheduleSrv = Annotated[ScheduleService, Depends(get_schedule_service)]
