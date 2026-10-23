from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from app.api.dependencies import CurrentUser
from app.schemas.duty import DutiesResponse, DutyAssignRequest
from app.services.duty_service import DutySrv

router = APIRouter(tags=["duties"])


@router.get("/duties", response_model=DutiesResponse)
async def get_duties(
    current_user: CurrentUser,
    service: DutySrv,
    group_id: int | None = None,
) -> DutiesResponse:
    return await service.get_duties(current_user, group_id)


@router.post("/duties/assign")
async def assign_duties(
    data: DutyAssignRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    service: DutySrv,
) -> dict:
    return await service.assign_duties(data, current_user, background_tasks)
