from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import DbSession
from app.db.redis_client import RedisClient
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

    async def _invalidate_permissions(self, user: User | None) -> None:
        if not user:
            return
        if user.tg_user_id:
            await invalidate_user_permissions(
                user.tg_user_id, self.redis, platform="telegram"
            )
        if user.vk_user_id:
            await invalidate_user_permissions(
                user.vk_user_id, self.redis, platform="vk"
            )

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

        group = await self.group_repo.create(
            name=body.name,
            tg_chat_id=body.tg_chat_id,
            vk_peer_id=body.vk_peer_id,
        )
        await self.session.commit()
        await self.group_repo.refresh(group)
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

        group = await self.group_repo.update(
            group=group,
            name=body.name,
            tg_chat_id=body.tg_chat_id,
            vk_peer_id=body.vk_peer_id,
        )
        await self.session.commit()
        await self.group_repo.refresh(group)
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

        members = await self.member_repo.get_members_with_users(group_id)
        await self.group_repo.delete_group(group)
        await self.session.commit()

        for user, _ in members:
            await self._invalidate_permissions(user)

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

        user = await self.user_repo.get_by_external_id(
            tg_user_id=body.tg_user_id,
            vk_user_id=body.vk_user_id,
        )

        if user is None:
            user = await self.user_repo.create(
                full_name=body.full_name,
                tg_user_id=body.tg_user_id,
                vk_user_id=body.vk_user_id,
            )
        else:
            if body.full_name and user.full_name != body.full_name:
                user = await self.user_repo.update(user, full_name=body.full_name)

        role_str = body.role.value if hasattr(body.role, "value") else str(body.role)
        member = await self.member_repo.upsert_member(
            group_id=group_id,
            user_id=user.id,
            role=role_str,
            is_duty_exempt=body.is_duty_exempt,
        )

        await self.session.commit()

        await self._invalidate_permissions(user)

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

        if body.tg_user_id is not None:
            conflict = await self.user_repo.get_by_tg_id_excluding(
                body.tg_user_id, user_id
            )
            if conflict:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"tg_user_id {body.tg_user_id} is already taken by another user",
                )

        if body.vk_user_id is not None:
            conflict_vk = await self.user_repo.get_by_vk_id_excluding(
                body.vk_user_id, user_id
            )
            if conflict_vk:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"vk_user_id {body.vk_user_id} is already taken by another user",
                )

        old_tg_id = user.tg_user_id
        old_vk_id = user.vk_user_id

        user = await self.user_repo.update(
            user=user,
            full_name=body.full_name,
            tg_user_id=body.tg_user_id,
            vk_user_id=body.vk_user_id,
        )

        role_str = (
            body.role.value
            if (body.role is not None and hasattr(body.role, "value"))
            else (str(body.role) if body.role is not None else None)
        )
        member = await self.member_repo.update_member(
            member=member,
            role=role_str,
            is_duty_exempt=body.is_duty_exempt,
        )

        await self.session.commit()

        await self._invalidate_permissions(user)
        if old_tg_id and old_tg_id != user.tg_user_id:
            await invalidate_user_permissions(
                old_tg_id, self.redis, platform="telegram"
            )
        if old_vk_id and old_vk_id != user.vk_user_id:
            await invalidate_user_permissions(old_vk_id, self.redis, platform="vk")

        return MemberResponse(
            user_id=user.id,
            full_name=user.full_name,
            tg_user_id=user.tg_user_id,
            vk_user_id=user.vk_user_id,
            role=member.role,
            is_duty_exempt=member.is_duty_exempt,
        )

    async def remove_member(self, group_id: int, user_id: int) -> None:
        user = await self.user_repo.get_by_id(user_id)
        deleted = await self.member_repo.remove_member(group_id, user_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in this group",
            )

        await self.session.commit()
        await self._invalidate_permissions(user)


def get_group_service(db: DbSession, redis: RedisClient) -> GroupService:
    return GroupService(
        session=db,
        group_repo=GroupRepository(db),
        member_repo=GroupMemberRepository(db),
        user_repo=UserRepository(db),
        redis=redis,
    )


GroupSrv = Annotated[GroupService, Depends(get_group_service)]
