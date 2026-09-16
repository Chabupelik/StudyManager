from __future__ import annotations

from datetime import datetime, timedelta

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.override import Override
from app.models.schedule_new import Lesson, Schedule

MSK = pytz.timezone("Europe/Moscow")
LESSON_DURATION_MINUTES = 90


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
                    "classroom": None,  # Overrides do not currently support changing classroom
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
