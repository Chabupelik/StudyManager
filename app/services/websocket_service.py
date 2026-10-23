from __future__ import annotations

import asyncio
import logging

from app.websocket.manager import manager

logger = logging.getLogger("studymanager_api")
_background_tasks: set[asyncio.Task] = set()


class WebSocketService:
    @classmethod
    async def _safe_broadcast(cls, message: dict) -> None:
        task = asyncio.create_task(cls._do_broadcast(message))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    @classmethod
    async def _do_broadcast(cls, message: dict) -> None:
        try:
            await manager.broadcast(message)
        except Exception as e:
            logger.warning("Failed to broadcast websocket event: %s", e)

    @classmethod
    async def broadcast_attendance(
        cls,
        date: str,
        time: str,
        student_id: int,
        status: int,
        reason: str | None,
    ) -> None:
        await cls._safe_broadcast(
            {
                "type": "update_attendance",
                "date": date,
                "time": time,
                "student_id": student_id,
                "status": status,
                "reason": reason,
            }
        )

    @classmethod
    async def broadcast_day_attendance(cls, date: str, student_id: int) -> None:
        await cls._safe_broadcast(
            {
                "type": "update_day",
                "date": date,
                "student_id": student_id,
            }
        )

    @classmethod
    async def broadcast_duties(cls) -> None:
        await cls._safe_broadcast({"type": "update_duties"})

    @classmethod
    async def broadcast_override(cls, date: str) -> None:
        await cls._safe_broadcast({"type": "override", "date": date})

    @classmethod
    async def broadcast_new_log(cls, entry: dict) -> None:
        await cls._safe_broadcast({"type": "new_log", "entry": entry})

    @classmethod
    async def broadcast_admin_status(cls, user_id: int, last_seen: float) -> None:
        await cls._safe_broadcast(
            {
                "type": "admin_status",
                "user_id": user_id,
                "last_seen": last_seen,
            }
        )
