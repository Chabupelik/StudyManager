from __future__ import annotations

import re
import time

import httpx

from app.core.config import get_settings


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


async def send_message(text: str, peer_id: int | None = None) -> None:
    settings = get_settings()
    target_peer_id = peer_id or settings.vk_chat_peer_id
    if not settings.vk_token or not target_peer_id:
        return

    params = {
        "peer_id": target_peer_id,
        "message": strip_html(text),
        "random_id": int(time.time() * 1000),
        "access_token": settings.vk_token,
        "v": settings.vk_api_version,
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                "https://api.vk.com/method/messages.send",
                data=params,
                timeout=10,
            )
        except Exception as e:
            print(f"[vk] send_message error: {e}")
