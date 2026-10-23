from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.models.group_member import MemberRole


class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    tg_chat_id: int | None = None
    vk_peer_id: int | None = None


class GroupUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
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
    is_duty_exempt: bool = False

    @model_validator(mode="after")
    def validate_ids(self) -> AddMemberRequest:
        if self.tg_user_id is None and self.vk_user_id is None:
            raise ValueError("Provide at least tg_user_id or vk_user_id")
        return self


class UpdateMemberRequest(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    tg_user_id: int | None = None
    vk_user_id: int | None = None
    role: MemberRole | None = None
    is_duty_exempt: bool | None = None


class MemberResponse(BaseModel):
    user_id: int
    full_name: str
    tg_user_id: int | None
    vk_user_id: int | None
    role: str
    is_duty_exempt: bool = False
