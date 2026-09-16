from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.student_repo import StudentRepository


class UserContext:
    __slots__ = ("first_name", "id", "platform", "username")

    def __init__(
        self,
        id: int,
        first_name: str = "",
        username: str | None = None,
        platform: str = "web",
    ) -> None:
        self.id = id
        self.first_name = first_name
        self.username = username
        self.platform = platform

    @property
    def is_developer(self) -> bool:
        return self.id == get_settings().developer_id

    @property
    def is_curator(self) -> bool:
        return self.id == get_settings().curator_id


_tg_id_to_name: dict[int, str] = {}
_id_to_name: dict[int, str] = {}
_id_to_tg: dict[int, int] = {}


async def load_student_cache(session: AsyncSession) -> None:
    global _tg_id_to_name, _id_to_name, _id_to_tg
    repo = StudentRepository(session)
    students = await repo.get_all()

    # Auto-seed if students table is empty
    if not students:
        from app.data.students_data import STUDENTS
        from app.models.student import Student

        for s in STUDENTS:
            session.add(Student(id=s["id"], name=s["name"], tg_id=s["tg_id"]))
        try:
            await session.commit()
            students = await repo.get_all()
        except Exception:
            await session.rollback()

    if students:
        _tg_id_to_name = {s.tg_id: s.name for s in students if s.tg_id}
        _id_to_name = {s.id: s.name for s in students}
        _id_to_tg = {s.id: s.tg_id for s in students if s.tg_id}
    else:
        from app.data.students_data import STUDENTS

        _tg_id_to_name = {s["tg_id"]: s["name"] for s in STUDENTS if s.get("tg_id")}
        _id_to_name = {s["id"]: s["name"] for s in STUDENTS}
        _id_to_tg = {s["id"]: s.get("tg_id", 0) for s in STUDENTS}

    # Also load from newer users table
    from sqlalchemy import select

    from app.models.user import User

    users = (await session.execute(select(User))).scalars().all()
    for u in users:
        if u.tg_user_id:
            _tg_id_to_name[u.tg_user_id] = u.full_name


def get_display_name(user: UserContext) -> str:
    settings = get_settings()
    if user.id == settings.curator_id:
        return "Виктория Александровна"
    name = _tg_id_to_name.get(user.id)
    if name:
        return name
    return user.first_name or f"Пользователь {user.id}"


def get_name_by_student_id(student_id: int) -> str:
    if not _id_to_name:
        from app.data.students_data import STUDENTS

        for s in STUDENTS:
            if s["id"] == student_id:
                return s["name"]
    return _id_to_name.get(student_id, f"Студент {student_id}")


def get_tg_by_student_id(student_id: int) -> int:
    return _id_to_tg.get(student_id, 0)


def get_role_label(user: UserContext) -> str:
    settings = get_settings()
    if user.id == settings.curator_id:
        return "куратор группы"
    if user.id == settings.developer_id:
        return "староста/разработчик"

    return "студент"


def get_full_name_by_tg(user: UserContext) -> str:
    settings = get_settings()
    if user.id == settings.curator_id:
        return "Виктория Александровна"
    if user.id == settings.developer_id:
        return "Максим Постнов"
    return _tg_id_to_name.get(user.id, "Пользователь")


def get_all_students() -> dict[int, str]:
    if not _id_to_name:
        from app.data.students_data import STUDENTS

        return {s["id"]: s["name"] for s in STUDENTS}
    return dict(_id_to_name)


def get_all_students_with_tg() -> list[dict]:
    if not _id_to_name:
        from app.data.students_data import STUDENTS

        return [
            {"id": s["id"], "name": s["name"], "tg_id": s.get("tg_id", 0)}
            for s in STUDENTS
        ]
    result = []
    for sid, name in _id_to_name.items():
        tg_id = _id_to_tg.get(sid, 0)
        result.append({"id": sid, "name": name, "tg_id": tg_id})
    return sorted(result, key=lambda x: x["id"])
