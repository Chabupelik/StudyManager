from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import Attendance
from app.models.override import Override
from app.models.schedule_new import Lesson, Schedule


def _build_override_map(overrides: list[Override]) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    for o in overrides:
        result[(o.date, o.time)] = {
            "name": o.new_name,
            "teacher": o.new_teacher,
            "canceled": bool(o.is_canceled),
        }
    return result


async def _get_base_lessons(
    session: AsyncSession, group_id: int
) -> list[tuple[Lesson, int]]:
    stmt = (
        select(Lesson, Schedule.day_of_week)
        .join(Schedule)
        .where(Schedule.group_id == group_id)
    )
    res = await session.execute(stmt)
    return res.all()  # [(Lesson, day_of_week), ...]


def compute_total_hours(
    overrides: list[Override],
    base_lessons: list[tuple[Lesson, int]],
    from_date_str: str,
    to_date_str: str,
) -> int:
    start_dt = datetime.strptime(from_date_str, "%Y-%m-%d").date()
    end_dt = datetime.strptime(to_date_str, "%Y-%m-%d").date()

    canceled_set = {(o.date, o.time) for o in overrides if o.is_canceled}
    added_set = {(o.date, o.time) for o in overrides if not o.is_canceled}

    total = 0
    curr = start_dt
    while curr <= end_dt:
        d_str = curr.strftime("%Y-%m-%d")
        wday = curr.weekday()

        # Find valid lessons for this date and weekday
        base_times = set()
        for l, day in base_lessons:
            if day == wday:
                if (l.valid_from is None or l.valid_from <= curr) and (
                    l.valid_until is None or l.valid_until >= curr
                ):
                    base_times.add(l.start_time.strftime("%H:%M"))

        count = sum(1 for t in base_times if (d_str, t) not in canceled_set)
        count += sum(1 for (dt, t) in added_set if dt == d_str and t not in base_times)
        total += count * 2
        curr += timedelta(days=1)

    return total


async def compute_month_hours(
    session: AsyncSession,
    group_id: int,
    year: int,
    month: int,
    overrides: list[Override],
) -> int:
    _, last_day = calendar.monthrange(year, month)
    from_str = f"{year}-{month:02d}-01"
    to_str = f"{year}-{month:02d}-{last_day:02d}"
    base_lessons = await _get_base_lessons(session, group_id)
    return compute_total_hours(overrides, base_lessons, from_str, to_str)


async def compute_lifetime_hours(
    session: AsyncSession, group_id: int, overrides: list[Override]
) -> int:
    base_lessons = await _get_base_lessons(session, group_id)

    start_dates = [l.valid_from for l, _ in base_lessons if l.valid_from]
    if not start_dates:
        return 0
    from_str = min(start_dates).strftime("%Y-%m-%d")
    to_str = datetime.now().strftime("%Y-%m-%d")

    return compute_total_hours(overrides, base_lessons, from_str, to_str)


def aggregate_student_stats(
    all_records: list[Attendance],
    month_records: list[Attendance],
) -> dict[int, dict]:
    total: dict[int, dict] = {}
    month: dict[int, dict] = {}

    for r in all_records:
        sid = r.user_id
        if sid not in total:
            total[sid] = {"nb": 0, "uv": 0}
        if r.status == 1:
            total[sid]["nb"] += 2
        elif r.status == 2:
            total[sid]["uv"] += 2

    for r in month_records:
        sid = r.user_id
        if sid not in month:
            month[sid] = {"nb": 0, "uv": 0}
        if r.status == 1:
            month[sid]["nb"] += 2
        elif r.status == 2:
            month[sid]["uv"] += 2

    return {"total": total, "month": month}


def _get_subject_at_memory(
    date_str: str,
    time_str: str,
    wday: int,
    override_map: dict[tuple[str, str], dict],
    base_lessons: list[tuple[Lesson, int]],
) -> tuple[str | None, str | None]:
    ovr = override_map.get((date_str, time_str))
    if ovr and ovr["canceled"]:
        return None, None
    if ovr and ovr["name"]:
        # Find teacher by name
        teacher = "Замена"
        for l, _ in base_lessons:
            if l.name == ovr["name"] and l.teacher:
                teacher = l.teacher
                break
        return ovr["name"], teacher

    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

    for l, day in base_lessons:
        if day == wday and l.start_time.strftime("%H:%M") == time_str:
            if (l.valid_from is None or l.valid_from <= date_obj) and (
                l.valid_until is None or l.valid_until >= date_obj
            ):
                return l.name, l.teacher
    return None, None


async def compute_subject_stats(
    session: AsyncSession,
    group_id: int,
    student_id: int,
    absences: list[Attendance],
    overrides: list[Override],
    month_prefix: str,
) -> list[dict]:
    override_map = _build_override_map(overrides)
    today_dt = datetime.now()

    base_lessons = await _get_base_lessons(session, group_id)

    start_dates = [l.valid_from for l, _ in base_lessons if l.valid_from]
    if not start_dates:
        return []
    earliest_dt = min(start_dates)
    if isinstance(earliest_dt, datetime):
        earliest_dt = earliest_dt.date()

    # Convert earliest_dt to datetime for loop
    curr_dt = datetime(earliest_dt.year, earliest_dt.month, earliest_dt.day)

    stats: dict[str, dict] = {}

    while curr_dt <= today_dt:
        d_str = curr_dt.strftime("%Y-%m-%d")
        wday = curr_dt.weekday()

        day_times = set()
        for l, day in base_lessons:
            if day == wday:
                if (l.valid_from is None or l.valid_from <= curr_dt.date()) and (
                    l.valid_until is None or l.valid_until >= curr_dt.date()
                ):
                    day_times.add(l.start_time.strftime("%H:%M"))

        day_times.update(t for (dt, t) in override_map.keys() if dt == d_str)

        for t_str in day_times:
            name, teacher = _get_subject_at_memory(
                d_str, t_str, wday, override_map, base_lessons
            )
            if name:
                if name not in stats:
                    stats[name] = {
                        "missed_m": 0,
                        "total_m": 0,
                        "missed_all": 0,
                        "total_all": 0,
                        "teacher": teacher,
                    }
                stats[name]["total_all"] += 2
                if d_str.startswith(month_prefix):
                    stats[name]["total_m"] += 2

        curr_dt += timedelta(days=1)

    for a in absences:
        d_str, t_str = a.date, a.time
        wday = datetime.strptime(d_str, "%Y-%m-%d").weekday()
        name, _ = _get_subject_at_memory(d_str, t_str, wday, override_map, base_lessons)
        if not name:
            name = "Доп. занятие"
        if name not in stats:
            stats[name] = {
                "missed_m": 0,
                "total_m": 0,
                "missed_all": 0,
                "total_all": 0,
                "teacher": "—",
            }
        stats[name]["missed_all"] += 2
        if d_str.startswith(month_prefix):
            stats[name]["missed_m"] += 2

    return [
        {
            "subject": name,
            "teacher": data["teacher"],
            "missed_month": data["missed_m"],
            "total_month": data["total_m"],
            "missed_all": data["missed_all"],
            "total_all": data["total_all"],
        }
        for name, data in stats.items()
        if data["total_all"] > 0 or data["missed_all"] > 0
    ]
