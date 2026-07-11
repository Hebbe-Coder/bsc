# app/orchestrator/sse.py
from __future__ import annotations
import asyncio
from typing import Dict


class SessionEventBus:
    """每会话一个 asyncio.Queue 的事件总线，供 SSE 端点消费。"""
    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}

    def get_queue(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    async def publish(self, session_id: str, event: dict):
        await self.get_queue(session_id).put(event)

    async def subscribe(self, session_id: str):
        q = self.get_queue(session_id)
        while True:
            yield await q.get()
