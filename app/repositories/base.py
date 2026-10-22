from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    model: type[ModelType] | None = None

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, instance: ModelType) -> ModelType:
        self.session.add(instance)
        return instance

    def add_all(self, instances: Sequence[ModelType]) -> Sequence[ModelType]:
        self.session.add_all(instances)
        return instances

    async def delete(self, instance: ModelType) -> None:
        await self.session.delete(instance)

    async def get_by_id(self, id: Any) -> ModelType | None:
        if self.model is None:
            raise NotImplementedError
        return await self.session.get(self.model, id)

    async def get_all(self) -> list[ModelType]:
        if self.model is None:
            raise NotImplementedError
        result = await self.session.execute(select(self.model))
        return list(result.scalars().all())

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, instance: ModelType) -> None:
        await self.session.refresh(instance)
