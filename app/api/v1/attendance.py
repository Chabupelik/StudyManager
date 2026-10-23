from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.schemas.attendance import AttendanceUpdateRequest, LessonDetailsResponse
from app.services.attendance_service import AttendanceSrv

router = APIRouter(tags=["attendance"])


@router.get("/lesson_details", response_model=LessonDetailsResponse)
async def get_lesson_details(
    date: str,
    time: str,
    group_id: int,
    current_user: CurrentUser,
    service: AttendanceSrv,
) -> LessonDetailsResponse:
    return await service.get_lesson_details(group_id, date, time, current_user)


@router.post("/attendance")
async def update_attendance(
    data: AttendanceUpdateRequest,
    current_user: CurrentUser,
    service: AttendanceSrv,
) -> dict:
    return await service.update_attendance(data, current_user)


@router.post("/attendance/day")
async def update_attendance_day(
    data: AttendanceUpdateRequest,
    current_user: CurrentUser,
    service: AttendanceSrv,
) -> dict:
    return await service.update_attendance_day(data, current_user)
