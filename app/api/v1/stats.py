from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.services.stats_service import StatsSrv

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats(
    year: str,
    month: str,
    current_user: CurrentUser,
    service: StatsSrv,
    group_id: int | None = None,
) -> dict:
    return await service.get_stats(year, month, current_user, group_id)


@router.get("/student_absences")
async def get_student_absences(
    student_id: int,
    current_user: CurrentUser,
    service: StatsSrv,
    group_id: int | None = None,
) -> dict:
    return await service.get_student_absences(student_id, current_user, group_id)


@router.get("/student_subject_stats")
async def get_student_subject_stats(
    student_id: int,
    year: str,
    month: str,
    current_user: CurrentUser,
    service: StatsSrv,
    group_id: int | None = None,
) -> dict:
    return await service.get_student_subject_stats(
        student_id, year, month, current_user, group_id
    )
