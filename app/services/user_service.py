from __future__ import annotations

from app.core.config import get_settings


class UserContext:
    __slots__ = ("first_name", "full_name", "id", "platform", "username")

    def __init__(
        self,
        id: int,
        first_name: str = "",
        full_name: str = "",
        username: str | None = None,
        platform: str = "web",
    ) -> None:
        self.id = id
        self.first_name = first_name
        self.full_name = full_name
        self.username = username
        self.platform = platform

    @property
    def is_developer(self) -> bool:
        return self.id == get_settings().developer_id


def get_display_name(user: UserContext) -> str:
    return user.full_name or user.first_name or f"Пользователь {user.id}"
