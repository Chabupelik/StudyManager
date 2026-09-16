#!/usr/bin/env python3
"""
Скрипт для миграции расписания из app.data.schedule_data в БД.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.data.schedule_data import BASE_SCHEDULES
from app.models.schedule_new import Lesson, Schedule

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

settings = get_settings()


def _parse_date(d: str) -> datetime.date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def _parse_time(t: str) -> datetime.time:
    return datetime.strptime(t, "%H:%M").time()


async def migrate() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        async with session.begin():
            # Idempotency: delete old data for groups being migrated
            for group_id in BASE_SCHEDULES.keys():
                log.info("Deleting old schedule for group %s", group_id)
                await session.execute(
                    Schedule.__table__.delete().where(Schedule.group_id == group_id)
                )

            for group_id, lessons_data in BASE_SCHEDULES.items():
                log.info("Migrating schedule for group %s", group_id)
                days = {item["day"] for item in lessons_data}
                schedule_map = {}
                for day in days:
                    sched = Schedule(group_id=group_id, day_of_week=day)
                    session.add(sched)
                    await session.flush()
                    schedule_map[day] = sched.id

                for idx, l in enumerate(lessons_data):
                    sched_id = schedule_map[l["day"]]
                    start_t = _parse_time(l["time"])

                    # Calculate end time (+90 mins)
                    start_h, start_m = start_t.hour, start_t.minute
                    dt = datetime(2000, 1, 1, start_h, start_m)
                    from datetime import timedelta

                    dt += timedelta(minutes=90)
                    end_t = dt.time()

                    lesson = Lesson(
                        schedule_id=sched_id,
                        lesson_number=idx + 1,
                        name=l["name"],
                        teacher=l.get("teacher"),
                        start_time=start_t,
                        end_time=end_t,
                        valid_from=_parse_date(l["start"]),
                        valid_until=_parse_date(l["end"]),
                    )
                    session.add(lesson)

        log.info("✅ Migration complete.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
