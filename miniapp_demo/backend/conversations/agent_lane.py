"""Per-conversation Agent Action FIFO queue."""
from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Literal, Optional


ActionKind = Literal["agent", "direct"]
ActionSource = Literal["chat", "ui"]
ActionState = Literal["queued", "running", "completed", "failed", "cancelled"]


@dataclass
class ActionRecord:
    action_id: str
    conversation_id: str
    kind: ActionKind
    source: ActionSource
    intent: str = ""
    name: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    skill_id: Optional[str] = None
    ui_instance_id: Optional[str] = None
    expected_revision: Optional[int] = None
    state: ActionState = "queued"


class DuplicateActionError(ValueError):
    pass


class AgentLane:
    def __init__(self) -> None:
        self._queue: Deque[ActionRecord] = deque()
        self._lock: Optional[asyncio.Lock] = None
        self._waiters: list[asyncio.Future[ActionRecord]] = []

    def _lane_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def enqueue(self, action: ActionRecord) -> int:
        async with self._lane_lock():
            self._queue.append(action)
            position = len(self._queue)
            if self._waiters:
                waiter = self._waiters.pop(0)
                if not waiter.done():
                    waiter.set_result(self._queue.popleft())
            return position

    async def dequeue(self) -> Optional[ActionRecord]:
        async with self._lane_lock():
            if self._queue:
                return self._queue.popleft()
            return None

    async def wait_next(self) -> ActionRecord:
        item = await self.dequeue()
        if item is not None:
            return item
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ActionRecord] = loop.create_future()
        self._waiters.append(future)
        return await future

    async def cancel(self, action_id: str) -> bool:
        async with self._lane_lock():
            for index, action in enumerate(self._queue):
                if action.action_id == action_id:
                    action.state = "cancelled"
                    del self._queue[index]
                    return True
            return False

    async def queue_length(self) -> int:
        async with self._lane_lock():
            return len(self._queue)


class ActionRegistry:
    """Idempotent action registration per conversation."""

    def __init__(self) -> None:
        self._seen: Dict[str, set[str]] = {}

    def register(self, conversation_id: str, action_id: str) -> Literal["accepted", "duplicate"]:
        seen = self._seen.setdefault(conversation_id, set())
        if action_id in seen:
            return "duplicate"
        seen.add(action_id)
        return "accepted"
