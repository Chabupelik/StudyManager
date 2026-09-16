from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from app.data.schedule_data import BASE_SCHEDULES
from app.models.attendance import Attendance
from app.models.override import Override
from app.services.schedule_service import get_subject_at


def _build_override_map(overrides: list[Override]) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    for o in overrides:
        result[(o.date, o.time)] = {
            "name": o.new_name,
            "teacher": o.new_teacher,
            "canceled": bool(o.is_canceled),
        }
    return result


def compute_total_hours(
    group_id: int, overrides: list[Override], from_date_str: str, to_date_str: str
) -> int:
    start_dt = datetime.strptime(from_date_str, "%Y-%m-%d")
    end_dt = datetime.strptime(to_date_str, "%Y-%m-%d")

    canceled_set = {(o.date, o.time) for o in overrides if o.is_canceled}
    added_set = {(o.date, o.time) for o in overrides if not o.is_canceled}

    total = 0
    curr = start_dt
    while curr <= end_dt:
        d_str = curr.strftime("%Y-%m-%d")
        wday = curr.weekday()
        base_schedule = BASE_SCHEDULES.get(group_id, [])
        base_times = {
            l["time"]
            for l in base_schedule
            if l["day"] == wday and l["start"] <= d_str <= l["end"]
        }
        count = sum(1 for t in base_times if (d_str, t) not in canceled_set)
        count += sum(1 for (dt, t) in added_set if dt == d_str and t not in base_times)
        total += count * 2
        curr += timedelta(days=1)

    return total


def compute_month_hours(
    group_id: int, year: int, month: int, overrides: list[Override]
) -> int:
    _, last_day = calendar.monthrange(year, month)
    from_str = f"{year}-{month:02d}-01"
    to_str = f"{year}-{month:02d}-{last_day:02d}"
    return compute_total_hours(group_id, overrides, from_str, to_str)


def compute_lifetime_hours(group_id: int, overrides: list[Override]) -> int:
    base_schedule = BASE_SCHEDULES.get(group_id, [])
    start_dates = [l["start"] for l in base_schedule]
    if not start_dates:
        return 0
    from_str = min(start_dates)
    to_str = datetime.now().strftime("%Y-%m-%d")
    return compute_total_hours(group_id, overrides, from_str, to_str)


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


def compute_subject_stats(
    group_id: int,
    student_id: int,
    absences: list[Attendance],
    overrides: list[Override],
    month_prefix: str,
) -> list[dict]:
    override_map = _build_override_map(overrides)
    today_dt = datetime.now()
    base_schedule = BASE_SCHEDULES.get(group_id, [])

    start_dates = [l["start"] for l in base_schedule]
    if not start_dates:
        return []
    earliest_dt = datetime.strptime(min(start_dates), "%Y-%m-%d")

    stats: dict[str, dict] = {}

    curr_dt = earliest_dt
    while curr_dt <= today_dt:
        d_str = curr_dt.strftime("%Y-%m-%d")
        wday = curr_dt.weekday()

        day_times: set[str] = {l["time"] for l in base_schedule if l["day"] == wday}
        day_times.update(t for (dt, t) in override_map.keys() if dt == d_str)

        for t_str in day_times:
            name, teacher = get_subject_at(group_id, d_str, t_str, wday, override_map)
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
        name, _ = get_subject_at(group_id, d_str, t_str, wday, override_map)
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
