from __future__ import annotations

from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    UserPermissionContext,
    get_current_user_context,
    require_group_role,
)
from app.db.database import get_db
from app.db.redis_client import get_redis
from app.models.group import Group
from app.models.group_member import GroupMember, MemberRole
from app.models.user import User
from app.services.permissions_service import invalidate_user_permissions

router = APIRouter(prefix="/groups", tags=["groups"])


class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    tg_chat_id: int | None = None
    vk_peer_id: int | None = None


class GroupResponse(BaseModel):
    id: int
    name: str
    tg_chat_id: int | None
    vk_peer_id: int | None


class AddMemberRequest(BaseModel):
    tg_user_id: int | None = None
    vk_user_id: int | None = None
    full_name: str = Field(..., min_length=1, max_length=255)
    role: MemberRole = MemberRole.student


class MemberResponse(BaseModel):
    user_id: int
    full_name: str
    tg_user_id: int | None
    vk_user_id: int | None
    role: str


@router.post("", response_model=GroupResponse, status_code=201)
async def create_group(
    body: GroupCreateRequest,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GroupResponse:
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")

    existing = await session.execute(select(Group).where(Group.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409, detail=f"Group '{body.name}' already exists"
        )

    group = Group(
        name=body.name,
        tg_chat_id=body.tg_chat_id,
        vk_peer_id=body.vk_peer_id,
    )
    session.add(group)
    await session.flush()
    return GroupResponse(
        id=group.id,
        name=group.name,
        tg_chat_id=group.tg_chat_id,
        vk_peer_id=group.vk_peer_id,
    )


class GroupUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    tg_chat_id: int | None = None
    vk_peer_id: int | None = None


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    body: GroupUpdateRequest,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GroupResponse:
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")

    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if body.name is not None and body.name != group.name:
        existing = await session.execute(select(Group).where(Group.name == body.name))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409, detail=f"Group '{body.name}' already exists"
            )
        group.name = body.name

    if body.tg_chat_id is not None:
        group.tg_chat_id = body.tg_chat_id
    if body.vk_peer_id is not None:
        group.vk_peer_id = body.vk_peer_id

    await session.flush()
    return GroupResponse(
        id=group.id,
        name=group.name,
        tg_chat_id=group.tg_chat_id,
        vk_peer_id=group.vk_peer_id,
    )


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def delete_group(
    group_id: int,
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
):
    if not ctx.is_superadmin:
        raise HTTPException(status_code=403, detail="Superadmin required")

    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    from sqlalchemy import delete

    from app.models.attendance import Attendance
    from app.models.duty import Duty

    await session.execute(delete(Attendance).where(Attendance.group_id == group_id))
    await session.execute(delete(Duty).where(Duty.group_id == group_id))

    await session.delete(group)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/my", response_model=list[GroupResponse])
async def get_my_groups(
    ctx: Annotated[UserPermissionContext, Depends(get_current_user_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[GroupResponse]:
    if ctx.is_superadmin:
        result = await session.execute(select(Group).order_by(Group.name))
        groups = result.scalars().all()
    else:
        group_ids = [int(gid) for gid in ctx.groups_roles]
        if not group_ids:
            return []
        result = await session.execute(
            select(Group).where(Group.id.in_(group_ids)).order_by(Group.name)
        )
        groups = result.scalars().all()

    return [
        GroupResponse(
            id=g.id,
            name=g.name,
            tg_chat_id=g.tg_chat_id,
            vk_peer_id=g.vk_peer_id,
        )
        for g in groups
    ]


@router.get(
    "/{group_id}/members",
    response_model=list[MemberResponse],
)
async def list_members(
    group_id: int,
    ctx: Annotated[
        UserPermissionContext,
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
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[MemberResponse]:
    stmt = (
        select(User, GroupMember)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
        .order_by(User.full_name)
    )
    rows = await session.execute(stmt)
    return [
        MemberResponse(
            user_id=user.id,
            full_name=user.full_name,
            tg_user_id=user.tg_user_id,
            vk_user_id=user.vk_user_id,
            role=member.role,
        )
        for user, member in rows.all()
    ]


@router.post("/{group_id}/members", response_model=MemberResponse, status_code=201)
async def add_member(
    group_id: int,
    body: AddMemberRequest,
    ctx: Annotated[
        UserPermissionContext,
        Depends(require_group_role([MemberRole.headman, MemberRole.curator])),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> MemberResponse:
    if body.tg_user_id is None and body.vk_user_id is None:
        raise HTTPException(
            status_code=422, detail="Provide at least tg_user_id or vk_user_id"
        )

    group = await session.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    user: User | None = None
    if body.tg_user_id:
        result = await session.execute(
            select(User).where(User.tg_user_id == body.tg_user_id)
        )
        user = result.scalar_one_or_none()

    if user is None and body.vk_user_id:
        result = await session.execute(
            select(User).where(User.vk_user_id == body.vk_user_id)
        )
        user = result.scalar_one_or_none()

    if user is None:
        user = User(
            tg_user_id=body.tg_user_id,
            vk_user_id=body.vk_user_id,
            full_name=body.full_name,
        )
        session.add(user)
        await session.flush()
    else:
        if body.full_name and user.full_name != body.full_name:
            user.full_name = body.full_name

    result = await session.execute(
        select(GroupMember).where(
            GroupMember.user_id == user.id,
            GroupMember.group_id == group_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        member = GroupMember(
            user_id=user.id,
            group_id=group_id,
            role=body.role,
        )
        session.add(member)
    else:
        member.role = body.role

    await session.flush()

    if user.tg_user_id:
        await invalidate_user_permissions(user.tg_user_id, redis)

    return MemberResponse(
        user_id=user.id,
        full_name=user.full_name,
        tg_user_id=user.tg_user_id,
        vk_user_id=user.vk_user_id,
        role=member.role,
    )


class UpdateMemberRequest(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    tg_user_id: int | None = None
    vk_user_id: int | None = None
    role: MemberRole | None = None


@router.put("/{group_id}/members/{user_id}", response_model=MemberResponse)
async def update_member(
    group_id: int,
    user_id: int,
    body: UpdateMemberRequest,
    ctx: Annotated[
        UserPermissionContext,
        Depends(require_group_role([MemberRole.headman, MemberRole.curator])),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> MemberResponse:
    result = await session.execute(
        select(GroupMember).where(
            GroupMember.user_id == user_id, GroupMember.group_id == group_id
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found in group")

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.tg_user_id is not None:
        conflict = await session.execute(
            select(User).where(
                User.tg_user_id == body.tg_user_id,
                User.id != user_id,
            )
        )
        if conflict.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"tg_user_id {body.tg_user_id} is already taken by another user",
            )
        user.tg_user_id = body.tg_user_id
    if body.vk_user_id is not None:
        user.vk_user_id = body.vk_user_id
    if body.role is not None:
        member.role = body.role

    await session.flush()
    if user.tg_user_id:
        await invalidate_user_permissions(user.tg_user_id, redis)

    return MemberResponse(
        user_id=user.id,
        full_name=user.full_name,
        tg_user_id=user.tg_user_id,
        vk_user_id=user.vk_user_id,
        role=member.role,
    )


@router.delete(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
async def remove_member(
    group_id: int,
    user_id: int,
    ctx: Annotated[
        UserPermissionContext,
        Depends(require_group_role([MemberRole.headman, MemberRole.curator])),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> Response:
    result = await session.execute(
        select(GroupMember).where(
            GroupMember.user_id == user_id,
            GroupMember.group_id == group_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found in this group")

    await session.delete(member)
    await session.flush()

    user = await session.get(User, user_id)
    if user and user.tg_user_id:
        await invalidate_user_permissions(user.tg_user_id, redis)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
