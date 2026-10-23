from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import get_settings
from app.models.group_member import MemberRole

_ADMIN_ROLES = frozenset(
    {
        MemberRole.headman.value,
        MemberRole.deputy.value,
        MemberRole.curator.value,
    }
)


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
    def is_developer(self) -> bool:
        settings = get_settings()
        return self.platform == "telegram" and self.id == settings.developer_id

    @property
    def display_name(self) -> str:
        return self.full_name or self.first_name or f"Пользователь {self.id}"

    def is_admin(self, group_id: int | str | None = None) -> bool:
        if self.is_superadmin:
            return True
        if group_id is not None:
            return self.groups_roles.get(str(group_id)) in _ADMIN_ROLES
        return any(role in _ADMIN_ROLES for role in self.groups_roles.values())

    def has_group_role(
        self, group_id: int | str, allowed_roles: set[str] | list[str]
    ) -> bool:
        if self.is_superadmin:
            return True
        return self.groups_roles.get(str(group_id)) in allowed_roles


def get_display_name(user: AuthUser) -> str:
    return user.display_name
