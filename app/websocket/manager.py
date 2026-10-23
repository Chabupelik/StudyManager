from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, message: dict) -> None:
        if not self._connections:
            return

        async def _send_one(ws: WebSocket) -> WebSocket | None:
            try:
                await asyncio.wait_for(ws.send_json(message), timeout=1.5)
                return None
            except Exception as e:
                logger.warning("Failed to send message to websocket client: %s", e)
                return ws

        results = await asyncio.gather(
            *[_send_one(ws) for ws in list(self._connections)],
            return_exceptions=True,
        )
        for res in results:
            if isinstance(res, WebSocket):
                self.disconnect(res)


manager = ConnectionManager()
