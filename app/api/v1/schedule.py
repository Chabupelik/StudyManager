from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from app.api.dependencies import CurrentUser
from app.schemas.schedule import OverrideUpdateRequest, ScheduleResponse
from app.services.schedule_service import ScheduleSrv

router = APIRouter(tags=["schedule"])


@router.get("/schedule", response_model=ScheduleResponse)
async def get_schedule(
    date: str,
    current_user: CurrentUser,
    service: ScheduleSrv,
    group_id: int | None = None,
) -> ScheduleResponse:
    return await service.get_schedule(date, current_user, group_id)


@router.post("/override")
async def update_override(
    data: OverrideUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    service: ScheduleSrv,
) -> dict:
    return await service.update_override(data, current_user, background_tasks)


@router.get("/admin/base", response_model=list[dict])
async def get_base_schedule(
    group_id: int,
    current_user: CurrentUser,
    service: ScheduleSrv,
) -> list[dict]:
    return await service.get_base_schedule(group_id, current_user)


@router.post("/admin/base/{group_id}/{day_of_week}")
async def create_base_lesson(
    group_id: int,
    day_of_week: int,
    data: dict,
    current_user: CurrentUser,
    service: ScheduleSrv,
) -> dict:
    return await service.create_base_lesson(group_id, day_of_week, data, current_user)


@router.put("/admin/base/lesson/{lesson_id}")
async def update_base_lesson(
    lesson_id: int,
    data: dict,
    current_user: CurrentUser,
    service: ScheduleSrv,
) -> dict:
    return await service.update_base_lesson(lesson_id, data, current_user)


@router.delete("/admin/base/lesson/{lesson_id}")
async def delete_base_lesson(
    lesson_id: int,
    current_user: CurrentUser,
    service: ScheduleSrv,
) -> dict:
    return await service.delete_base_lesson(lesson_id, current_user)
