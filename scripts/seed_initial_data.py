#!/usr/bin/env python3
"""
Idempotent seed script: создаёт группу "37АБД", переносит студентов
и куратора из существующей таблицы students (и STAFF-хардкода) в
таблицы users + group_members.

Запуск:
    docker compose exec backend python scripts/seed_initial_data.py

Скрипт безопасен для повторного запуска (все операции — upsert/get-or-create).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# Ensure the project root is on the path when run directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (read directly to avoid circular imports at script startup)
# ---------------------------------------------------------------------------
from app.core.config import get_settings  # noqa: E402

settings = get_settings()

# ---------------------------------------------------------------------------
# Staff list (curator + any VK-only users not in the students table).
# Mirrors the hardcoded list used by the old dependencies.py.
# tg_id is the Telegram user ID; vk_id is optional.
# ---------------------------------------------------------------------------
STAFF_SEED: list[dict] = [
    {
        "name": "Виктория Александровна",
        "tg_id": 1331701095,
        "vk_id": None,
        "role": "curator",
    },
]

# Role assignment logic (applied to students from the DB):
#   DEVELOPER_ID       → headman + is_superadmin
#   ADMIN_IDS (legacy) → deputy
#   Everyone else      → student
HEADMAN_TG_ID: int = settings.developer_id  # 620159705 — Постнов Максим
DEPUTY_TG_IDS: set[int] = set(settings.admin_ids_list) - {HEADMAN_TG_ID}
CURATOR_TG_IDS: set[int] = {1331701095}

GROUP_NAME = "37АБД"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def get_or_create_group(session: AsyncSession) -> int:
    """Return group.id, creating the group if it does not exist."""
    from app.models.group import Group

    result = await session.execute(select(Group).where(Group.name == GROUP_NAME))
    group = result.scalar_one_or_none()
    if group is None:
        group = Group(name=GROUP_NAME)
        session.add(group)
        await session.flush()  # populate group.id
        log.info("Created group '%s' (id=%s)", GROUP_NAME, group.id)
    else:
        log.info("Group '%s' already exists (id=%s)", GROUP_NAME, group.id)
    return group.id


async def upsert_user(
    session: AsyncSession,
    *,
    full_name: str,
    tg_id: int | None,
    vk_id: int | None = None,
    is_superadmin: bool = False,
) -> int:
    """Return user.id, creating or updating the user record."""
    from app.models.user import User

    user: User | None = None

    # Try to find by tg_id first, then vk_id.
    if tg_id:
        result = await session.execute(select(User).where(User.tg_user_id == tg_id))
        user = result.scalar_one_or_none()

    if user is None and vk_id:
        result = await session.execute(select(User).where(User.vk_user_id == vk_id))
        user = result.scalar_one_or_none()

    if user is None:
        user = User(
            tg_user_id=tg_id,
            vk_user_id=vk_id,
            full_name=full_name,
            is_superadmin=is_superadmin,
        )
        session.add(user)
        await session.flush()
        log.info("  Created user '%s' (id=%s, tg=%s)", full_name, user.id, tg_id)
    else:
        # Update mutable fields in case they changed.
        user.full_name = full_name
        if is_superadmin:
            user.is_superadmin = True
        if tg_id and user.tg_user_id is None:
            user.tg_user_id = tg_id
        if vk_id and user.vk_user_id is None:
            user.vk_user_id = vk_id
        log.info("  Found user '%s' (id=%s)", full_name, user.id)

    return user.id


async def upsert_member(
    session: AsyncSession,
    *,
    user_id: int,
    group_id: int,
    role: str,
) -> None:
    """Create or update a group_members row."""
    from app.models.group_member import GroupMember

    result = await session.execute(
        select(GroupMember).where(
            GroupMember.user_id == user_id,
            GroupMember.group_id == group_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        session.add(GroupMember(user_id=user_id, group_id=group_id, role=role))
        log.info("    → member role=%s (user_id=%s)", role, user_id)
    else:
        if member.role != role:
            log.info(
                "    → updated role %s→%s (user_id=%s)", member.role, role, user_id
            )
            member.role = role
        else:
            log.info("    → role already=%s (user_id=%s)", role, user_id)


def _assign_role(tg_id: int | None) -> str:
    if tg_id == HEADMAN_TG_ID:
        return "headman"
    if tg_id in DEPUTY_TG_IDS:
        return "deputy"
    if tg_id in CURATOR_TG_IDS:
        return "curator"
    return "student"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def seed() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        async with session.begin():
            # 1. Group
            group_id = await get_or_create_group(session)

            # 2. Students from the existing `students` table
            log.info("Loading students from DB...")
            rows = await session.execute(
                text("SELECT id, name, tg_id FROM students ORDER BY id")
            )
            students = rows.fetchall()
            log.info("Found %d students in DB.", len(students))

            for row in students:
                _, name, tg_id = row  # (db_id, name, tg_id)
                tg_id = int(tg_id) if tg_id else None
                role = _assign_role(tg_id)
                is_super = tg_id == HEADMAN_TG_ID

                user_id = await upsert_user(
                    session,
                    full_name=name,
                    tg_id=tg_id,
                    is_superadmin=is_super,
                )
                await upsert_member(
                    session, user_id=user_id, group_id=group_id, role=role
                )

            # 3. STAFF (curator and any extra staff not in students table)
            log.info("Seeding staff...")
            for staff in STAFF_SEED:
                tg_id = staff.get("tg_id")
                vk_id = staff.get("vk_id")
                # Skip if already added via students table
                if tg_id:
                    existing = await session.execute(
                        text("SELECT id FROM users WHERE tg_user_id = :t"),
                        {"t": tg_id},
                    )
                    if existing.scalar_one_or_none() is not None:
                        log.info(
                            "  Staff '%s' already seeded, skipping.", staff["name"]
                        )
                        continue

                user_id = await upsert_user(
                    session,
                    full_name=staff["name"],
                    tg_id=tg_id,
                    vk_id=vk_id,
                    is_superadmin=False,
                )
                await upsert_member(
                    session,
                    user_id=user_id,
                    group_id=group_id,
                    role=staff["role"],
                )

        log.info("✅ Seed complete.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
