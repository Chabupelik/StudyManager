from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import DbSession
from app.models.attendance import Attendance
from app.models.override import Override
from app.models.schedule_new import Lesson
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.override_repo import OverrideRepository
from app.repositories.schedule_repo import ScheduleRepository
from app.repositories.user_repo import UserRepository
from app.services.schedule_service import compute_active_times
from app.services.user_service import AuthUser


def _build_override_map(overrides: list[Override]) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    for o in overrides:
        result[(o.date, o.time)] = {
            "name": o.new_name,
            "teacher": o.new_teacher,
            "canceled": bool(o.is_canceled),
        }
    return result


def _compute_base_times_for_date_memory(
    date_str: str,
    base_lessons: list[tuple[Lesson, int]],
) -> set[str]:
    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    wday = date_obj.weekday()
    base_times = set()
    for l, day in base_lessons:
        if day == wday:
            if (l.valid_from is None or l.valid_from <= date_obj) and (
                l.valid_until is None or l.valid_until >= date_obj
            ):
                base_times.add(l.start_time.strftime("%H:%M"))
    return base_times


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


def get_semester_dates(year: int, month: int) -> tuple[str, str]:
    if 9 <= month <= 12:
        return f"{year}-09-01", f"{year}-12-31"
    else:
        return f"{year}-01-01", f"{year}-08-31"


def compute_lifetime_hours(
    base_lessons: list[tuple[Lesson, int]], overrides: list[Override]
) -> int:
    start_dates = [l.valid_from for l, _ in base_lessons if l.valid_from]
    if not start_dates:
        return 0
    from_str = min(start_dates).strftime("%Y-%m-%d")
    to_str = datetime.now().strftime("%Y-%m-%d")
    return compute_total_hours(overrides, base_lessons, from_str, to_str)


def aggregate_student_stats(
    semester_records: list[Attendance],
    month_records: list[Attendance],
) -> dict[str, dict[int, dict[str, int]]]:
    total: dict[int, dict[str, int]] = {}
    month: dict[int, dict[str, int]] = {}

    for r in semester_records:
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


def compute_subject_stats(
    student_id: int,
    absences: list[Attendance],
    overrides: list[Override],
    base_lessons: list[tuple[Lesson, int]],
    month_prefix: str,
    semester_start: str | None = None,
    semester_end: str | None = None,
) -> list[dict]:
    override_map = _build_override_map(overrides)
    today_dt = datetime.now()

    if semester_start:
        sem_start_dt = datetime.strptime(semester_start, "%Y-%m-%d").date()
        curr_dt = datetime(sem_start_dt.year, sem_start_dt.month, sem_start_dt.day)
    else:
        start_dates = [l.valid_from for l, _ in base_lessons if l.valid_from]
        if not start_dates:
            return []
        earliest_dt = min(start_dates)
        if isinstance(earliest_dt, datetime):
            earliest_dt = earliest_dt.date()
        curr_dt = datetime(earliest_dt.year, earliest_dt.month, earliest_dt.day)

    if semester_end:
        sem_end_dt = datetime.strptime(semester_end, "%Y-%m-%d")
        end_limit = min(sem_end_dt, today_dt)
    else:
        end_limit = today_dt

    stats: dict[str, dict] = {}

    while curr_dt <= end_limit:
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
        if semester_start and not (
            semester_start <= a.date <= (semester_end or "9999-12-31")
        ):
            continue
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


class StatsService:
    def __init__(
        self,
        session: AsyncSession,
        att_repo: AttendanceRepository,
        ovr_repo: OverrideRepository,
        user_repo: UserRepository,
        schedule_repo: ScheduleRepository,
    ) -> None:
        self.session = session
        self.att_repo = att_repo
        self.ovr_repo = ovr_repo
        self.user_repo = user_repo
        self.schedule_repo = schedule_repo

    def _parse_year_month(self, year: str, month: str) -> tuple[int, int, str]:
        try:
            y_int = int(year)
            m_int = int(month)
            if m_int < 1 or m_int > 12:
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid year or month format",
            )
        month_prefix = f"{y_int}-{m_int:02d}-"
        return y_int, m_int, month_prefix

    def _resolve_target_group(
        self, group_id: int | None, current_user: AuthUser
    ) -> int | None:
        if not current_user.groups_roles and not current_user.is_superadmin:
            return None
        if group_id is not None:
            if (
                not current_user.is_superadmin
                and str(group_id) not in current_user.groups_roles
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
                )
            return group_id
        return (
            int(next(iter(current_user.groups_roles.keys())))
            if current_user.groups_roles
            else 1
        )

    async def get_stats(
        self,
        year: str,
        month: str,
        current_user: AuthUser,
        group_id: int | None = None,
    ) -> dict:
        y_int, m_int, month_prefix = self._parse_year_month(year, month)
        target_group_id = self._resolve_target_group(group_id, current_user)
        if target_group_id is None:
            return {
                "total_month_hours": 0,
                "total_lifetime_hours": 0,
                "total_semester_hours": 0,
                "stats": [],
            }

        sem_start, sem_end = get_semester_dates(y_int, m_int)
        _, last_day = calendar.monthrange(y_int, m_int)
        month_start = f"{y_int}-{m_int:02d}-01"
        month_end = f"{y_int}-{m_int:02d}-{last_day:02d}"

        semester_records = await self.att_repo.get_stats_for_period(
            target_group_id, sem_start, sem_end
        )
        month_records = await self.att_repo.get_stats_for_month(
            target_group_id, month_prefix
        )
        overrides = await self.ovr_repo.get_for_group(target_group_id)
        base_lessons = await self.schedule_repo.get_lessons_with_days(target_group_id)

        aggregated = aggregate_student_stats(semester_records, month_records)
        total_month_hours = compute_total_hours(
            overrides, base_lessons, month_start, month_end
        )
        total_semester_hours = compute_total_hours(
            overrides, base_lessons, sem_start, sem_end
        )
        total_lifetime_hours = compute_lifetime_hours(base_lessons, overrides)

        users = await self.user_repo.get_group_students(target_group_id)

        result = []
        for u in users:
            sid = u.id
            t = aggregated["total"].get(sid, {"nb": 0, "uv": 0})
            m = aggregated["month"].get(sid, {"nb": 0, "uv": 0})
            result.append(
                {
                    "id": sid,
                    "tg_id": u.tg_user_id or 0,
                    "name": u.full_name,
                    "total_nb": t["nb"],
                    "total_uv": t["uv"],
                    "month_nb": m["nb"],
                    "month_uv": m["uv"],
                }
            )

        return {
            "total_month_hours": total_month_hours,
            "total_lifetime_hours": total_lifetime_hours,
            "total_semester_hours": total_semester_hours,
            "stats": result,
        }

    async def get_student_absences(
        self,
        student_id: int,
        current_user: AuthUser,
        group_id: int | None = None,
    ) -> dict:
        target_group_id = self._resolve_target_group(group_id, current_user)
        if target_group_id is None:
            return {"absences": []}

        absences = await self.att_repo.get_student_absences(target_group_id, student_id)
        overrides = await self.ovr_repo.get_for_group(target_group_id)
        base_lessons = await self.schedule_repo.get_lessons_with_days(target_group_id)

        override_map = _build_override_map(overrides)

        result = []
        day_totals: dict[str, int] = {}

        for a in absences:
            d_str, t_str = a.date, a.time
            weekday = datetime.strptime(d_str, "%Y-%m-%d").weekday()

            if d_str not in day_totals:
                base_times = _compute_base_times_for_date_memory(d_str, base_lessons)
                day_ovrs = [o for o in overrides if o.date == d_str]
                active = compute_active_times(base_times, day_ovrs)
                day_totals[d_str] = len(active) * 2

            name, _ = _get_subject_at_memory(
                d_str, t_str, weekday, override_map, base_lessons
            )
            if not name:
                name = "Доп. занятие"

            result.append(
                {
                    "date": d_str,
                    "time": t_str,
                    "name": name,
                    "status": a.status,
                    "reason": a.reason,
                    "day_total_hours": day_totals[d_str],
                }
            )

        result.sort(key=lambda x: (x["date"], x["time"].zfill(5)), reverse=True)
        return {"absences": result}

    async def get_student_subject_stats(
        self,
        student_id: int,
        year: str,
        month: str,
        current_user: AuthUser,
        group_id: int | None = None,
    ) -> dict:
        y_int, m_int, month_prefix = self._parse_year_month(year, month)
        target_group_id = self._resolve_target_group(group_id, current_user)
        if target_group_id is None:
            return {"subjects": []}

        sem_start, sem_end = get_semester_dates(y_int, m_int)

        absences = await self.att_repo.get_student_absences(target_group_id, student_id)
        overrides = await self.ovr_repo.get_for_group(target_group_id)
        base_lessons = await self.schedule_repo.get_lessons_with_days(target_group_id)

        subjects = compute_subject_stats(
            student_id,
            absences,
            overrides,
            base_lessons,
            month_prefix,
            sem_start,
            sem_end,
        )
        return {"subjects": subjects}


def get_stats_service(db: DbSession) -> StatsService:
    return StatsService(
        session=db,
        att_repo=AttendanceRepository(db),
        ovr_repo=OverrideRepository(db),
        user_repo=UserRepository(db),
        schedule_repo=ScheduleRepository(db),
    )


StatsSrv = Annotated[StatsService, Depends(get_stats_service)]
