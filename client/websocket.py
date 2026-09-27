"""WebSocket client helper with reconnect (Python side; primary WS runs in UI JS)."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

import websockets


class ChatWebSocket:
    def __init__(
        self,
        base_url: str,
        token: str,
        on_event: Callable[[dict[str, Any]], Awaitable[None] | None],
    ) -> None:
        self.ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + f"/ws?token={token}"
        self.on_event = on_event
        self._stop = False

    async def run(self) -> None:
        delay = 1.0
        while not self._stop:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
                    delay = 1.0
                    async for raw in ws:
                        data = json.loads(raw)
                        result = self.on_event(data)
                        if asyncio.iscoroutine(result):
                            await result
            except Exception:
                if self._stop:
                    break
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)

    def stop(self) -> None:
        self._stop = True
