from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import UserPermissionContext, get_current_user_context
from app.db.database import get_db
from app.models.group_member import GroupMember, MemberRole
from app.models.user import User
from app.repositories.attendance_repo import AttendanceRepository
from app.repositories.override_repo import OverrideRepository
from app.services.stats_service import (
    aggregate_student_stats,
    compute_lifetime_hours,
    compute_month_hours,
    compute_subject_stats,
)

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats(
    year: str,
    month: str,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    month_prefix = f"{year}-{month}-"

    if not ctx.groups_roles and not ctx.is_superadmin:
        return {"total_month_hours": 0, "total_lifetime_hours": 0, "stats": []}
    group_id = int(next(iter(ctx.groups_roles.keys()))) if ctx.groups_roles else 1

    att_repo = AttendanceRepository(db)
    ovr_repo = OverrideRepository(db)

    all_records = await att_repo.get_all_stats(group_id)
    month_records = await att_repo.get_stats_for_month(group_id, month_prefix)
    overrides = await ovr_repo.get_all()

    aggregated = aggregate_student_stats(all_records, month_records)
    total_month_hours = await compute_month_hours(
        db, group_id, int(year), int(month), overrides
    )
    total_lifetime_hours = await compute_lifetime_hours(db, group_id, overrides)

    stmt = (
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(
            GroupMember.group_id == group_id,
            GroupMember.role.in_(
                [MemberRole.student, MemberRole.headman, MemberRole.deputy]
            ),
        )
        .order_by(User.full_name)
    )
    users = (await db.execute(stmt)).scalars().all()

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
        "stats": result,
    }


@router.get("/student_absences")
async def get_student_absences(
    student_id: int,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    if not ctx.groups_roles and not ctx.is_superadmin:
        return {"absences": []}
    group_id = int(next(iter(ctx.groups_roles.keys()))) if ctx.groups_roles else 1

    att_repo = AttendanceRepository(db)
    ovr_repo = OverrideRepository(db)

    absences = await att_repo.get_student_absences(group_id, student_id)
    overrides = await ovr_repo.get_all()

    from app.services.schedule_service import get_subject_at
    from app.services.stats_service import _build_override_map

    override_map = _build_override_map(overrides)

    result = []
    day_totals: dict[str, int] = {}

    for a in absences:
        d_str, t_str = a.date, a.time
        weekday = datetime.strptime(d_str, "%Y-%m-%d").weekday()

        if d_str not in day_totals:
            from app.services.schedule_service import (
                compute_active_times,
                get_base_times_for_date,
            )

            base_times = await get_base_times_for_date(db, group_id, d_str)
            day_ovrs = [o for o in overrides if o.date == d_str]
            active = compute_active_times(base_times, day_ovrs)
            day_totals[d_str] = len(active) * 2

        name, _ = await get_subject_at(
            db, group_id, d_str, t_str, weekday, override_map
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


@router.get("/student_subject_stats")
async def get_student_subject_stats(
    student_id: int,
    year: str,
    month: str,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    db: AsyncSession = Depends(get_db),
):
    month_prefix = f"{year}-{month}-"

    if not ctx.groups_roles and not ctx.is_superadmin:
        return {"subjects": []}
    group_id = int(next(iter(ctx.groups_roles.keys()))) if ctx.groups_roles else 1

    att_repo = AttendanceRepository(db)
    ovr_repo = OverrideRepository(db)

    absences = await att_repo.get_student_absences(group_id, student_id)
    overrides = await ovr_repo.get_all()

    subjects = await compute_subject_stats(
        db, group_id, student_id, absences, overrides, month_prefix
    )
    return {"subjects": subjects}
