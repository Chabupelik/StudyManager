from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import DbSession
from app.db.redis_client import RedisClient
from app.models.group import Group
from app.models.group_member import GroupMember
from app.models.user import User
from app.repositories.group_member_repo import GroupMemberRepository
from app.repositories.group_repo import GroupRepository
from app.repositories.user_repo import UserRepository
from app.schemas.group import (
    AddMemberRequest,
    GroupCreateRequest,
    GroupResponse,
    GroupUpdateRequest,
    MemberResponse,
    UpdateMemberRequest,
)
from app.services.permissions_service import invalidate_user_permissions
from app.services.user_service import AuthUser


class GroupService:
    def __init__(
        self,
        session: AsyncSession,
        group_repo: GroupRepository,
        member_repo: GroupMemberRepository,
        user_repo: UserRepository,
        redis: RedisClient,
    ) -> None:
        self.session = session
        self.group_repo = group_repo
        self.member_repo = member_repo
        self.user_repo = user_repo
        self.redis = redis

    async def create_group(
        self, body: GroupCreateRequest, current_user: AuthUser
    ) -> GroupResponse:
        if not current_user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superadmin required",
            )

        existing = await self.group_repo.get_by_name(body.name)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Group '{body.name}' already exists",
            )

        group = Group(
            name=body.name,
            tg_chat_id=body.tg_chat_id,
            vk_peer_id=body.vk_peer_id,
        )
        self.group_repo.add(group)
        await self.session.commit()
        await self.session.refresh(group)
        return GroupResponse(
            id=group.id,
            name=group.name,
            tg_chat_id=group.tg_chat_id,
            vk_peer_id=group.vk_peer_id,
        )

    async def update_group(
        self,
        group_id: int,
        body: GroupUpdateRequest,
        current_user: AuthUser,
    ) -> GroupResponse:
        if not current_user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superadmin required",
            )

        group = await self.group_repo.get_by_id(group_id)
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        if body.name is not None and body.name != group.name:
            existing = await self.group_repo.get_by_name(body.name)
            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Group '{body.name}' already exists",
                )
            group.name = body.name

        if body.tg_chat_id is not None:
            group.tg_chat_id = body.tg_chat_id
        if body.vk_peer_id is not None:
            group.vk_peer_id = body.vk_peer_id

        await self.session.commit()
        await self.session.refresh(group)
        return GroupResponse(
            id=group.id,
            name=group.name,
            tg_chat_id=group.tg_chat_id,
            vk_peer_id=group.vk_peer_id,
        )

    async def delete_group(self, group_id: int, current_user: AuthUser) -> None:
        if not current_user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superadmin required",
            )

        group = await self.group_repo.get_by_id(group_id)
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        await self.group_repo.delete_group_related_data(group_id)
        await self.group_repo.delete(group)
        await self.session.commit()

    async def get_my_groups(self, current_user: AuthUser) -> list[GroupResponse]:
        if current_user.is_superadmin:
            groups = await self.group_repo.get_all_ordered_by_name()
        else:
            group_ids = [int(gid) for gid in current_user.groups_roles]
            if not group_ids:
                return []
            groups = await self.group_repo.get_by_ids_ordered_by_name(group_ids)

        return [
            GroupResponse(
                id=g.id,
                name=g.name,
                tg_chat_id=g.tg_chat_id,
                vk_peer_id=g.vk_peer_id,
            )
            for g in groups
        ]

    async def list_members(self, group_id: int) -> list[MemberResponse]:
        rows = await self.member_repo.get_members_with_users(group_id)
        return [
            MemberResponse(
                user_id=user.id,
                full_name=user.full_name,
                tg_user_id=user.tg_user_id,
                vk_user_id=user.vk_user_id,
                role=member.role,
                is_duty_exempt=member.is_duty_exempt,
            )
            for user, member in rows
        ]

    async def add_member(self, group_id: int, body: AddMemberRequest) -> MemberResponse:
        if body.tg_user_id is None and body.vk_user_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide at least tg_user_id or vk_user_id",
            )

        group = await self.group_repo.get_by_id(group_id)
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Group not found",
            )

        user: User | None = None
        if body.tg_user_id:
            user = await self.user_repo.get_by_tg_id(body.tg_user_id)

        if user is None and body.vk_user_id:
            user = await self.user_repo.get_by_vk_id(body.vk_user_id)

        if user is None:
            user = User(
                tg_user_id=body.tg_user_id,
                vk_user_id=body.vk_user_id,
                full_name=body.full_name,
            )
            self.user_repo.add(user)
            await self.session.flush()
        else:
            if body.full_name and user.full_name != body.full_name:
                user.full_name = body.full_name

        member = await self.member_repo.get_member(group_id, user.id)
        if member is None:
            member = GroupMember(
                user_id=user.id,
                group_id=group_id,
                role=body.role,
                is_duty_exempt=body.is_duty_exempt,
            )
            self.member_repo.add(member)
        else:
            member.role = body.role
            member.is_duty_exempt = body.is_duty_exempt

        await self.session.commit()

        if user.tg_user_id:
            await invalidate_user_permissions(user.tg_user_id, self.redis)

        return MemberResponse(
            user_id=user.id,
            full_name=user.full_name,
            tg_user_id=user.tg_user_id,
            vk_user_id=user.vk_user_id,
            role=member.role,
            is_duty_exempt=member.is_duty_exempt,
        )

    async def update_member(
        self, group_id: int, user_id: int, body: UpdateMemberRequest
    ) -> MemberResponse:
        member = await self.member_repo.get_member(group_id, user_id)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in group",
            )

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        if body.full_name is not None:
            user.full_name = body.full_name
        if body.tg_user_id is not None:
            conflict = await self.user_repo.get_by_tg_id_excluding(
                body.tg_user_id, user_id
            )
            if conflict:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"tg_user_id {body.tg_user_id} is already taken by another user",
                )
            user.tg_user_id = body.tg_user_id
        if body.vk_user_id is not None:
            user.vk_user_id = body.vk_user_id
        if body.role is not None:
            member.role = body.role
        if body.is_duty_exempt is not None:
            member.is_duty_exempt = body.is_duty_exempt

        await self.session.commit()
        if user.tg_user_id:
            await invalidate_user_permissions(user.tg_user_id, self.redis)

        return MemberResponse(
            user_id=user.id,
            full_name=user.full_name,
            tg_user_id=user.tg_user_id,
            vk_user_id=user.vk_user_id,
            role=member.role,
            is_duty_exempt=member.is_duty_exempt,
        )

    async def remove_member(self, group_id: int, user_id: int) -> None:
        member = await self.member_repo.get_member(group_id, user_id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in this group",
            )

        await self.member_repo.delete(member)
        await self.session.commit()

        user = await self.user_repo.get_by_id(user_id)
        if user and user.tg_user_id:
            await invalidate_user_permissions(user.tg_user_id, self.redis)


def get_group_service(db: DbSession, redis: RedisClient) -> GroupService:
    return GroupService(
        session=db,
        group_repo=GroupRepository(db),
        member_repo=GroupMemberRepository(db),
        user_repo=UserRepository(db),
        redis=redis,
    )


GroupSrv = Annotated[GroupService, Depends(get_group_service)]
