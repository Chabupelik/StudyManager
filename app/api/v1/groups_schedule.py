from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import require_group_role
from app.models.group_member import MemberRole
from app.schemas.groups_schedule import (
    LessonCreateRequest,
    LessonResponse,
    ScheduleCreateRequest,
    ScheduleResponse,
    TodayLessonResponse,
)
from app.services.groups_schedule_service import GroupsScheduleSrv
from app.services.user_service import AuthUser

router = APIRouter(prefix="/groups", tags=["schedule"])

CanManageSchedule = Annotated[
    AuthUser,
    Depends(require_group_role([MemberRole.headman, MemberRole.curator])),
]
CanViewSchedule = Annotated[
    AuthUser,
    Depends(
        require_group_role(
            [
                MemberRole.student,
                MemberRole.deputy,
                MemberRole.headman,
                MemberRole.curator,
            ]
        )
    ),
]


@router.post(
    "/{group_id}/schedules",
    response_model=ScheduleResponse,
    status_code=201,
)
async def create_schedule(
    group_id: int,
    body: ScheduleCreateRequest,
    user: CanManageSchedule,
    service: GroupsScheduleSrv,
) -> ScheduleResponse:
    return await service.create_schedule(group_id, body, user)


@router.post(
    "/{group_id}/schedules/{schedule_id}/lessons",
    response_model=LessonResponse,
    status_code=201,
)
async def add_lesson(
    group_id: int,
    schedule_id: int,
    body: LessonCreateRequest,
    user: CanManageSchedule,
    service: GroupsScheduleSrv,
) -> LessonResponse:
    return await service.add_lesson(group_id, schedule_id, body, user)


@router.get(
    "/{group_id}/schedule/today",
    response_model=TodayLessonResponse,
)
async def get_today_schedule(
    group_id: int,
    user: CanViewSchedule,
    service: GroupsScheduleSrv,
) -> TodayLessonResponse:
    return await service.get_today_schedule(group_id, user)


@router.get(
    "/{group_id}/schedule",
    response_model=list[ScheduleResponse],
)
async def get_full_schedule(
    group_id: int,
    user: CanViewSchedule,
    service: GroupsScheduleSrv,
) -> list[ScheduleResponse]:
    return await service.get_full_schedule(group_id, user)
