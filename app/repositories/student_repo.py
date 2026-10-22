from __future__ import annotations

from sqlalchemy import select

from app.models.student import Student
from app.repositories.base import BaseRepository


class StudentRepository(BaseRepository[Student]):
    model = Student

    async def get_all(self) -> list[Student]:
        result = await self.session.execute(select(Student).order_by(Student.id))
        return list(result.scalars().all())

    async def get_by_tg_id(self, tg_id: int) -> Student | None:
        result = await self.session.execute(
            select(Student).where(Student.tg_id == tg_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, student_id: int) -> Student | None:
        result = await self.session.execute(
            select(Student).where(Student.id == student_id)
        )
        return result.scalar_one_or_none()
