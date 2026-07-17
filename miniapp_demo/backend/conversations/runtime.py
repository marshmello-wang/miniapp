"""Conversation runtime orchestration."""
from __future__ import annotations

import asyncio
import threading
from typing import Any, AsyncIterator, Dict, Optional, Set, Tuple
from uuid import uuid4

from common.agent_framework.user_interface.content_blocks import TextBlock

from .. import stores
from .agent_events import agent_event_to_durable
from .agent_lane import (
    ActionRecord,
    ActionRegistry,
    AgentLane,
    DuplicateActionError,
)
from .agent_worker import run_unified_agent_turn
from .context_builder import build_turn_context
from .context_projector import project_business_context
from .direct_relay import DirectRelay
from .event_store import EventStore
from .protocol import make_durable_event

_SNAPSHOT_TIMEOUT_UI = 5.0


class ConversationRuntime:
    def __init__(self, event_store: EventStore, *, user: str = "local"):
        self.event_store = event_store
        self.user = user
        self.direct_relay = DirectRelay(user=user)
        self._lanes: Dict[str, AgentLane] = {}
        self._registries: Dict[str, ActionRegistry] = {}
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._subscriber_lock = threading.RLock()
        self._snapshot_waiters: Dict[Tuple[str, str], asyncio.Future] = {}
        self._locked_ui: Dict[str, str] = {}
        self._processors: Dict[str, asyncio.Task] = {}

    def lane_for(self, conversation_id: str) -> AgentLane:
        if conversation_id not in self._lanes:
            self._lanes[conversation_id] = AgentLane()
        return self._lanes[conversation_id]

    def registry_for(self, conversation_id: str) -> ActionRegistry:
        if conversation_id not in self._registries:
            self._registries[conversation_id] = ActionRegistry()
        return self._registries[conversation_id]

    async def submit_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        conversation_id = payload["conversationId"]
        action_id = payload["actionId"]
        registry = self.registry_for(conversation_id)
        if registry.register(conversation_id, action_id) == "duplicate":
            raise DuplicateActionError(action_id)

        record = ActionRecord(
            action_id=action_id,
            conversation_id=conversation_id,
            kind=payload["kind"],
            source=payload["source"],
            intent=payload.get("intent") or "",
            name=payload.get("name") or "",
            args=dict(payload.get("args") or {}),
            skill_id=payload.get("skillId"),
            ui_instance_id=payload.get("uiInstanceId"),
            expected_revision=payload.get("expectedRevision"),
        )

        await self._emit(
            conversation_id,
            make_durable_event(
                conversation_id=conversation_id,
                event_type="action.accepted",
                actor="runtime",
                action_id=action_id,
                skill_id=record.skill_id,
                ui_instance_id=record.ui_instance_id,
                payload={"kind": record.kind, "source": record.source},
            ),
        )

        if record.kind == "agent":
            lane = self.lane_for(conversation_id)
            position = await lane.enqueue(record)
            await self._emit(
                conversation_id,
                make_durable_event(
                    conversation_id=conversation_id,
                    event_type="agent_action.enqueued",
                    actor="runtime",
                    action_id=action_id,
                    skill_id=record.skill_id,
                    ui_instance_id=record.ui_instance_id,
                    payload={"queuePosition": position},
                ),
            )
            if record.ui_instance_id:
                self._locked_ui[record.ui_instance_id] = action_id
                await self._emit(
                    conversation_id,
                    make_durable_event(
                        conversation_id=conversation_id,
                        event_type="ui.loading.changed",
                        actor="runtime",
                        action_id=action_id,
                        ui_instance_id=record.ui_instance_id,
                        payload={"loading": True},
                    ),
                )
            self._ensure_processor(conversation_id)
            return {"status": "enqueued", "queuePosition": position}

        if record.ui_instance_id and record.ui_instance_id in self._locked_ui:
            await self._emit(
                conversation_id,
                make_durable_event(
                    conversation_id=conversation_id,
                    event_type="direct_action.failed",
                    actor="runtime",
                    action_id=action_id,
                    skill_id=record.skill_id,
                    ui_instance_id=record.ui_instance_id,
                    payload={"error": "UI locked by agent action"},
                ),
            )
            return {"status": "failed", "error": "UI locked by agent action"}

        await self._emit(
            conversation_id,
            make_durable_event(
                conversation_id=conversation_id,
                event_type="direct_action.started",
                actor="runtime",
                action_id=action_id,
                skill_id=record.skill_id,
                ui_instance_id=record.ui_instance_id,
                payload={"name": record.name},
            ),
        )
        relay_result = await self.direct_relay.execute(record)
        if relay_result.ok:
            for command in relay_result.ui_commands:
                await self._emit(
                    conversation_id,
                    make_durable_event(
                        conversation_id=conversation_id,
                        event_type="ui.command",
                        actor="runtime",
                        action_id=action_id,
                        skill_id=record.skill_id,
                        ui_instance_id=record.ui_instance_id,
                        payload=command,
                    ),
                )
            await self._emit(
                conversation_id,
                make_durable_event(
                    conversation_id=conversation_id,
                    event_type="direct_action.completed",
                    actor="runtime",
                    action_id=action_id,
                    skill_id=record.skill_id,
                    ui_instance_id=record.ui_instance_id,
                    payload={"summary": relay_result.summary},
                ),
            )
            return {"status": "completed"}

        await self._emit(
            conversation_id,
            make_durable_event(
                conversation_id=conversation_id,
                event_type="direct_action.failed",
                actor="runtime",
                action_id=action_id,
                skill_id=record.skill_id,
                ui_instance_id=record.ui_instance_id,
                payload={"error": relay_result.error or "direct action failed"},
            ),
        )
        return {"status": "failed", "error": relay_result.error}

    async def submit_snapshot(
        self,
        conversation_id: str,
        action_id: str,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        key = (conversation_id, action_id)
        future = self._snapshot_waiters.get(key)
        if future is None or future.done():
            return {"status": "ignored"}
        future.set_result(body)
        await self._emit(
            conversation_id,
            make_durable_event(
                conversation_id=conversation_id,
                event_type="ui.snapshot.received",
                actor="runtime",
                action_id=action_id,
                skill_id=body.get("skillId"),
                ui_instance_id=body.get("uiInstanceId"),
                payload={"snapshotRequestId": body.get("snapshotRequestId")},
            ),
        )
        return {"status": "accepted"}

    async def cancel_action(self, conversation_id: str, action_id: str) -> bool:
        lane = self.lane_for(conversation_id)
        cancelled = await lane.cancel(action_id)
        if cancelled:
            await self._emit(
                conversation_id,
                make_durable_event(
                    conversation_id=conversation_id,
                    event_type="agent_action.cancelled",
                    actor="runtime",
                    action_id=action_id,
                    payload={},
                ),
            )
        return cancelled

    async def subscribe(
        self,
        conversation_id: str,
        *,
        after: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue()
        with self._subscriber_lock:
            self._subscribers.setdefault(conversation_id, set()).add(queue)

        for event in self.event_store.replay(conversation_id, after=after):
            yield event

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            with self._subscriber_lock:
                subs = self._subscribers.get(conversation_id)
                if subs and queue in subs:
                    subs.remove(queue)

    def _ensure_processor(self, conversation_id: str) -> None:
        task = self._processors.get(conversation_id)
        if task is not None and not task.done():
            return
        self._processors[conversation_id] = asyncio.create_task(
            self._processor_loop(conversation_id)
        )

    async def _processor_loop(self, conversation_id: str) -> None:
        lane = self.lane_for(conversation_id)
        while True:
            action = await lane.wait_next()
            await self._execute_agent_action(action)

    async def _execute_agent_action(self, record: ActionRecord) -> None:
        conversation_id = record.conversation_id
        action_id = record.action_id
        try:
            await self._emit(
                conversation_id,
                make_durable_event(
                    conversation_id=conversation_id,
                    event_type="agent_action.started",
                    actor="runtime",
                    action_id=action_id,
                    skill_id=record.skill_id,
                    ui_instance_id=record.ui_instance_id,
                    payload={},
                ),
            )

            business_context = await self._collect_business_context(record)
            user_intent = record.intent or ""
            if not user_intent and record.args:
                user_intent = str(record.args)
            turn = build_turn_context(
                user_intent=user_intent,
                business_context=business_context,
            )

            history = stores.load_history_rich(conversation_id)
            stores.ensure_conversation_session(conversation_id, username=self.user)
            round_idx = stores.start_round_rich(
                conversation_id,
                user_intent or "(agent action)",
                source=record.source,
            )
            task_id = f"conv_{uuid4().hex[:12]}"
            store_dir = str(stores.business_store_dir(conversation_id))

            ai_text_parts: list[str] = []
            trajectory: list[Dict[str, Any]] = []

            async for agent_event in self._stream_agent_turn(
                conversation_id=conversation_id,
                task_id=task_id,
                turn=turn,
                history=history,
                store_dir=store_dir,
            ):
                if isinstance(agent_event, tuple) and agent_event[0] == "__error__":
                    raise RuntimeError(str(agent_event[1]))
                try:
                    trajectory.append(agent_event.to_dict())
                except Exception:
                    pass
                for block in getattr(agent_event, "content", []) or []:
                    if isinstance(block, TextBlock):
                        ai_text_parts.append(block.text)
                for partial in agent_event_to_durable(agent_event, action_id=action_id):
                    await self._emit(
                        conversation_id,
                        make_durable_event(
                            conversation_id=conversation_id,
                            event_type=partial["type"],
                            actor="agent" if partial["type"].startswith("agent.") else "runtime",
                            action_id=action_id,
                            skill_id=record.skill_id,
                            ui_instance_id=record.ui_instance_id,
                            payload=partial["payload"],
                        ),
                    )

            ai_text = "".join(ai_text_parts).strip() or "(no text output)"
            stores.complete_round(
                conversation_id,
                round_idx,
                ai_text,
                trajectory=trajectory,
            )
            await self._emit(
                conversation_id,
                make_durable_event(
                    conversation_id=conversation_id,
                    event_type="agent_action.completed",
                    actor="runtime",
                    action_id=action_id,
                    skill_id=record.skill_id,
                    ui_instance_id=record.ui_instance_id,
                    payload={"roundIdx": round_idx},
                ),
            )
        except Exception as exc:  # noqa: BLE001
            await self._emit(
                conversation_id,
                make_durable_event(
                    conversation_id=conversation_id,
                    event_type="agent_action.failed",
                    actor="runtime",
                    action_id=action_id,
                    skill_id=record.skill_id,
                    ui_instance_id=record.ui_instance_id,
                    payload={"error": str(exc)},
                ),
            )
        finally:
            if record.ui_instance_id and self._locked_ui.get(record.ui_instance_id) == action_id:
                self._locked_ui.pop(record.ui_instance_id, None)
                await self._emit(
                    conversation_id,
                    make_durable_event(
                        conversation_id=conversation_id,
                        event_type="ui.loading.changed",
                        actor="runtime",
                        action_id=action_id,
                        ui_instance_id=record.ui_instance_id,
                        payload={"loading": False},
                    ),
                )

    async def _collect_business_context(
        self,
        record: ActionRecord,
    ) -> Optional[Dict[str, Any]]:
        needs_snapshot = bool(record.ui_instance_id or record.skill_id)
        if not needs_snapshot:
            return None

        snapshot_request_id = f"snap_{record.action_id}"
        await self._emit(
            record.conversation_id,
            make_durable_event(
                conversation_id=record.conversation_id,
                event_type="ui.snapshot.requested",
                actor="runtime",
                action_id=record.action_id,
                skill_id=record.skill_id,
                ui_instance_id=record.ui_instance_id,
                payload={"snapshotRequestId": snapshot_request_id},
            ),
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._snapshot_waiters[(record.conversation_id, record.action_id)] = future
        timeout = _SNAPSHOT_TIMEOUT_UI if record.ui_instance_id else 0.5
        try:
            view_snapshot = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            if record.ui_instance_id:
                raise RuntimeError("UI_SNAPSHOT_UNAVAILABLE") from None
            return None
        finally:
            self._snapshot_waiters.pop((record.conversation_id, record.action_id), None)

        if not record.skill_id:
            return {
                "skillId": view_snapshot.get("skillId"),
                "uiInstanceId": view_snapshot.get("uiInstanceId"),
                "route": view_snapshot.get("route"),
                "revision": view_snapshot.get("revision"),
                "view": dict(view_snapshot.get("env") or {}),
                "business": {},
            }
        return await project_business_context(
            skill_id=record.skill_id,
            view_snapshot=view_snapshot,
            user=self.user,
        )

    async def _stream_agent_turn(
        self,
        *,
        conversation_id: str,
        task_id: str,
        turn,
        history,
        store_dir: str,
    ):
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()
        stop_event = threading.Event()

        def offer(item) -> None:
            if not stop_event.is_set():
                queue.put_nowait(item)

        def worker():
            try:
                source = run_unified_agent_turn(
                    conversation_id=conversation_id,
                    task_id=task_id,
                    turn=turn,
                    rich_history=history,
                    store_dir=store_dir,
                )
                for event in source:
                    if stop_event.is_set():
                        break
                    loop.call_soon_threadsafe(offer, event)
            except Exception as exc:  # noqa: BLE001
                if not stop_event.is_set():
                    loop.call_soon_threadsafe(offer, ("__error__", exc))
            finally:
                if not stop_event.is_set():
                    loop.call_soon_threadsafe(offer, sentinel)

        threading.Thread(target=worker, daemon=True).start()
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                yield item
        finally:
            stop_event.set()

    async def _emit(self, conversation_id: str, event: Dict[str, Any]) -> Dict[str, Any]:
        seq = self.event_store.append(event)
        stored = self.event_store.replay(conversation_id, after=seq - 1)[0]
        with self._subscriber_lock:
            for queue in self._subscribers.get(conversation_id, set()):
                queue.put_nowait(stored)
        return stored
