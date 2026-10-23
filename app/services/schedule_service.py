from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

import pytz
from fastapi import BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import DbSession, async_session_maker
from app.models.override import Override
from app.models.schedule_new import Lesson, Schedule
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.override_repo import OverrideRepository
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.schedule import OverrideUpdateRequest, ScheduleResponse
from app.services.audit_service import log_action
from app.services.user_service import AuthUser, get_display_name
from app.websocket.manager import manager

MSK = pytz.timezone("Europe/Moscow")
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
    weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

    stmt = (
        select(Lesson.start_time)
        .join(Schedule)
        .where(
            Schedule.group_id == group_id,
            Schedule.day_of_week == weekday,
            (Lesson.valid_from <= date_obj) | (Lesson.valid_from.is_(None)),
            (Lesson.valid_until >= date_obj) | (Lesson.valid_until.is_(None)),
        )
    )
    result = await session.execute(stmt)
    times = result.scalars().all()
    return {t.strftime("%H:%M") for t in times}


async def get_base_lessons_for_date(
    session: AsyncSession, group_id: int, date_str: str
) -> list[dict]:
    weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

    stmt = (
        select(Lesson)
        .join(Schedule)
        .where(
            Schedule.group_id == group_id,
            Schedule.day_of_week == weekday,
            (Lesson.valid_from <= date_obj) | (Lesson.valid_from.is_(None)),
            (Lesson.valid_until >= date_obj) | (Lesson.valid_until.is_(None)),
        )
        .order_by(Lesson.start_time)
    )
    result = await session.execute(stmt)
    lessons = result.scalars().all()

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

    if ovr and ovr["name"]:
        stmt = (
            select(Lesson.teacher)
            .join(Schedule)
            .where(Schedule.group_id == group_id, Lesson.name == ovr["name"])
            .limit(1)
        )
        res = await session.execute(stmt)
        teacher = res.scalar_one_or_none() or "Замена"
        return ovr["name"], teacher

    stmt = (
        select(Lesson)
        .join(Schedule)
        .where(
            Schedule.group_id == group_id,
            Schedule.day_of_week == weekday,
            Lesson.start_time == datetime.strptime(time_str, "%H:%M").time(),
            (Lesson.valid_from <= date_obj) | (Lesson.valid_from.is_(None)),
            (Lesson.valid_until >= date_obj) | (Lesson.valid_until.is_(None)),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    match = result.scalar_one_or_none()

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
    ) -> None:
        self.session = session
        self.schedule_repo = schedule_repo
        self.att_repo = att_repo
        self.ovr_repo = ovr_repo

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

        if (
            not current_user.is_superadmin
            and str(target_group_id) not in current_user.groups_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

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

        if (
            not current_user.is_superadmin
            and str(target_group_id) not in current_user.groups_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

        if not current_user.is_superadmin and current_user.groups_roles.get(
            str(target_group_id)
        ) not in [
            "headman",
            "deputy",
            "curator",
        ]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

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
        await manager.broadcast({"type": "override", "date": data.date})

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
        if (
            not current_user.is_superadmin
            and str(group_id) not in current_user.groups_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

        schedules, lessons = await self.schedule_repo.get_base_lessons_with_schedules(
            group_id
        )

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
                        for l in day_lessons
                    ],
                }
            )
        return res

    async def create_base_lesson(
        self,
        group_id: int,
        day_of_week: int,
        data: dict,
        current_user: AuthUser,
    ) -> dict:
        if (
            not current_user.is_superadmin
            and str(group_id) not in current_user.groups_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

        schedule = await self.schedule_repo.get_by_group_and_day(group_id, day_of_week)
        if not schedule:
            schedule = Schedule(group_id=group_id, day_of_week=day_of_week)
            self.schedule_repo.add(schedule)
            await self.session.flush()

        lesson = Lesson(
            schedule_id=schedule.id,
            lesson_number=data.get("lesson_number", 1),
            name=data["name"],
            teacher=data.get("teacher"),
            classroom=data.get("classroom"),
            start_time=datetime.strptime(data["start_time"], "%H:%M").time(),
            end_time=datetime.strptime(data["end_time"], "%H:%M").time(),
            valid_from=(
                datetime.strptime(data["valid_from"], "%Y-%m-%d").date()
                if data.get("valid_from")
                else None
            ),
            valid_until=(
                datetime.strptime(data["valid_until"], "%Y-%m-%d").date()
                if data.get("valid_until")
                else None
            ),
        )
        self.schedule_repo.add_lesson(lesson)
        await self.session.commit()
        return {"status": "ok", "id": lesson.id}

    async def update_base_lesson(
        self,
        lesson_id: int,
        data: dict,
        current_user: AuthUser,
    ) -> dict:
        lesson = await self.schedule_repo.get_lesson_by_id(lesson_id)
        if not lesson:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lesson not found",
            )

        schedule = await self.schedule_repo.get_by_id(lesson.schedule_id)
        if not schedule or (
            not current_user.is_superadmin
            and str(schedule.group_id) not in current_user.groups_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

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

        await self.session.commit()
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
        if not schedule or (
            not current_user.is_superadmin
            and str(schedule.group_id) not in current_user.groups_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

        await self.schedule_repo.delete_lesson(lesson)
        await self.session.commit()
        return {"status": "ok"}


def get_schedule_service(db: DbSession) -> ScheduleService:
    return ScheduleService(
        session=db,
        schedule_repo=ScheduleRepository(db),
        att_repo=AttendanceRepository(db),
        ovr_repo=OverrideRepository(db),
    )


ScheduleSrv = Annotated[ScheduleService, Depends(get_schedule_service)]
