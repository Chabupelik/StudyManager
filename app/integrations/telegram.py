from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def send_message(
    chat_id: str | int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: dict | None = None,
) -> dict | None:
    settings = get_settings()
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.bot_token}/sendMessage",
                json=payload,
                timeout=10,
            )
            data = resp.json()
            if not data.get("ok"):
                logger.error(
                    "[telegram] sendMessage error: %s", data.get("description")
                )
            return data
        except Exception:
            logger.exception("[telegram] sendMessage failed for chat_id=%s", chat_id)
            return None


async def check_membership(user_id: int) -> str | None:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"https://api.telegram.org/bot{settings.bot_token}/getChatMember",
                params={"chat_id": settings.group_id, "user_id": user_id},
                timeout=10,
            )
            data = resp.json()
            if data.get("ok"):
                return data.get("result", {}).get("status")
            logger.error(
                "[telegram] getChatMember error for user_id=%s: %s",
                user_id,
                data.get("description"),
            )
        except Exception:
            logger.exception("[telegram] getChatMember failed for user_id=%s", user_id)
    return None
