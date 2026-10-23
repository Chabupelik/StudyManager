from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import CurrentUser, require_group_role
from app.models.group_member import MemberRole
from app.schemas.group import (
    AddMemberRequest,
    GroupCreateRequest,
    GroupResponse,
    GroupUpdateRequest,
    MemberResponse,
    UpdateMemberRequest,
)
from app.services.group_service import GroupSrv
from app.services.user_service import AuthUser

router = APIRouter(prefix="/groups", tags=["groups"])

CanManageMembers = Annotated[
    AuthUser,
    Depends(require_group_role([MemberRole.headman, MemberRole.curator])),
]
CanViewMembers = Annotated[
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


@router.post("", response_model=GroupResponse, status_code=201)
async def create_group(
    body: GroupCreateRequest,
    current_user: CurrentUser,
    service: GroupSrv,
) -> GroupResponse:
    return await service.create_group(body, current_user)


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    body: GroupUpdateRequest,
    current_user: CurrentUser,
    service: GroupSrv,
) -> GroupResponse:
    return await service.update_group(group_id, body, current_user)


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_group(
    group_id: int,
    current_user: CurrentUser,
    service: GroupSrv,
) -> Response:
    await service.delete_group(group_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/my", response_model=list[GroupResponse])
async def get_my_groups(
    current_user: CurrentUser,
    service: GroupSrv,
) -> list[GroupResponse]:
    return await service.get_my_groups(current_user)


@router.get(
    "/{group_id}/members",
    response_model=list[MemberResponse],
)
async def list_members(
    group_id: int,
    user: CanViewMembers,
    service: GroupSrv,
) -> list[MemberResponse]:
    return await service.list_members(group_id)


@router.post("/{group_id}/members", response_model=MemberResponse, status_code=201)
async def add_member(
    group_id: int,
    body: AddMemberRequest,
    user: CanManageMembers,
    service: GroupSrv,
) -> MemberResponse:
    return await service.add_member(group_id, body)


@router.put("/{group_id}/members/{user_id}", response_model=MemberResponse)
async def update_member(
    group_id: int,
    user_id: int,
    body: UpdateMemberRequest,
    user: CanManageMembers,
    service: GroupSrv,
) -> MemberResponse:
    return await service.update_member(group_id, user_id, body)


@router.delete(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def remove_member(
    group_id: int,
    user_id: int,
    user: CanManageMembers,
    service: GroupSrv,
) -> Response:
    await service.remove_member(group_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
