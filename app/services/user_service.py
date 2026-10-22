from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import get_settings


@dataclass(slots=True)
class AuthUser:
    id: int
    first_name: str = ""
    full_name: str = ""
    username: str | None = None
    platform: str = "telegram"
    is_superadmin: bool = False
    groups_roles: dict[str, str] = field(default_factory=dict)

    @property
    def user(self) -> AuthUser:
        return self

    @property
    def is_developer(self) -> bool:
        return self.id == get_settings().developer_id

    @property
    def display_name(self) -> str:
        return self.full_name or self.first_name or f"Пользователь {self.id}"

    def is_admin(self, group_id: int | str | None = None) -> bool:
        if self.is_superadmin:
            return True
        if group_id is not None:
            return self.groups_roles.get(str(group_id)) in (
                "headman",
                "deputy",
                "curator",
            )
        return any(
            role in ("headman", "deputy", "curator")
            for role in self.groups_roles.values()
        )

    def has_group_role(
        self, group_id: int | str, allowed_roles: set[str] | list[str]
    ) -> bool:
        if self.is_superadmin:
            return True
        return self.groups_roles.get(str(group_id)) in allowed_roles


UserContext = AuthUser


def get_display_name(user: AuthUser) -> str:
    return user.display_name
