from __future__ import annotations

from app.models.group import Group
from app.repositories.base import BaseRepository


class GroupRepository(BaseRepository[Group]):
    model = Group
