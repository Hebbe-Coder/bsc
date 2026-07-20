from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import AsyncIterator

from app.orchestrator.contracts import EventType, OrchestratorEvent
from app.orchestrator.event_store import EventStore


_CLOSE = object()


class SessionEventBus:
    def __init__(
        self,
        history_limit: int = 256,
        event_store: EventStore | None = None,
    ):
        self._history_limit = history_limit
        self._history: dict[str, deque[OrchestratorEvent]] = defaultdict(
            lambda: deque(maxlen=self._history_limit)
        )
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._seq: dict[str, int] = {}
        self._event_store = event_store
        self._lock = asyncio.Lock()

    async def publish(
        self,
        session_id: str,
        event_type: EventType | str | dict,
        *,
        stage: str = "pipeline",
        status: str = "",
        message: str = "",
        terminal: bool = False,
        data: dict | None = None,
    ) -> OrchestratorEvent:
        if isinstance(event_type, dict):
            legacy = event_type
            stage = legacy.get("stage", stage)
            status = legacy.get("status", status if status else "running")
            message = legacy.get("msg", legacy.get("message", message))
            event_type = {
                "running": EventType.STAGE_STARTED,
                "done": EventType.STAGE_COMPLETED,
                "loopback": EventType.STAGE_LOOPBACK,
            }.get(status, EventType.STAGE_COMPLETED)
            data = {**(data or {}), "legacy": True}
        async with self._lock:
            previous_seq = self._seq.get(session_id)
            if previous_seq is None:
                previous_seq = (
                    self._event_store.last_seq(session_id)
                    if self._event_store is not None
                    else 0
                )
            event = OrchestratorEvent(
                session_id=session_id,
                seq=previous_seq + 1,
                type=event_type,
                stage=stage,
                status=status,
                message=message,
                terminal=terminal,
                data=data or {},
            )
            if self._event_store is not None:
                self._event_store.append(event)
            self._seq[session_id] = event.seq
            self._history[session_id].append(event)
            subscribers = tuple(self._subscribers.get(session_id, ()))

        for queue in subscribers:
            await queue.put(event)
        return event

    async def subscribe(
        self,
        session_id: str,
        after: int = 0,
    ) -> AsyncIterator[OrchestratorEvent]:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            if self._event_store is not None:
                replay = self._event_store.events_after(session_id, after)
                latest = self._event_store.latest_event(session_id)
                session_terminal = bool(latest and latest.terminal)
            else:
                history = tuple(self._history.get(session_id, ()))
                replay = [event for event in history if event.seq > after]
                session_terminal = bool(history and history[-1].terminal)
            if not session_terminal:
                self._subscribers[session_id].add(queue)

        try:
            for event in replay:
                yield event
                if event.terminal:
                    return
            if session_terminal:
                return
            while True:
                item = await queue.get()
                if item is _CLOSE:
                    return
                yield item
                if item.terminal:
                    return
        finally:
            async with self._lock:
                self._subscribers[session_id].discard(queue)
                if not self._subscribers[session_id]:
                    self._subscribers.pop(session_id, None)

    async def close(self, session_id: str) -> None:
        async with self._lock:
            subscribers = tuple(self._subscribers.pop(session_id, ()))
        for queue in subscribers:
            await queue.put(_CLOSE)
