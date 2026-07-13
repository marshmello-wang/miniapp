"""ChatEngine: chat 对话引擎。

与 MiniAppEngine 类似,但面向通用 chat session:
- chat_action: 读历史 + 跑 chat agent(dynamic skills) + 流式事件
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from common.agent_framework.user_interface.content_blocks import TextBlock

from . import protocol, stores
from .chat_agent_runner import run_chat_agent


class ChatEngine:
    async def chat_action(
        self,
        session_id: str,
        intent: str,
        request_id: str,
    ) -> AsyncIterator[Dict[str, Any]]:
        seq = protocol.SeqCounter()
        history = stores.load_history(session_id)

        round_idx = stores.start_round(session_id, intent or "(chat)", source="chat")

        task_id = f"chat_{uuid4().hex[:12]}"
        trajectory: List[Dict[str, Any]] = []
        ai_text_parts: List[str] = []
        terminal_frame: Optional[Dict[str, Any]] = None
        error_text: Optional[str] = None

        _INTERNAL_EVENTS = frozenset((
            "orchestration_start", "orchestration_complete",
            "node_start", "node_complete",
        ))

        async for item in self._stream_chat(session_id, task_id, intent, history):
            if isinstance(item, tuple) and item and item[0] == "__error__":
                error_text = str(item[1])
                break
            ev = item
            try:
                trajectory.append(ev.to_dict())
            except Exception:
                pass
            if ev.event_type in _INTERNAL_EVENTS:
                continue
            for block in ev.content:
                if isinstance(block, TextBlock):
                    ai_text_parts.append(block.text)
            frames = protocol.frames_for_event(ev, session_id, request_id, seq)
            for frame in frames:
                frame["data_type"] = "chat.event"
                if frame["data"]["type"] == "done":
                    frame["data"]["payload"]["roundIdx"] = round_idx
                    terminal_frame = frame
                else:
                    yield frame

        if error_text is not None:
            yield _chat_frame(protocol.make_event_frame(
                "text", session_id, request_id, seq.next(),
                {"delta": f"[error] {error_text}", "final": True},
            ))
            terminal_frame = _chat_frame(protocol.make_event_frame(
                "done", session_id, request_id, seq.next(),
                {"status": "error", "error": error_text, "roundIdx": round_idx},
            ))
        elif terminal_frame is None:
            terminal_frame = _chat_frame(protocol.make_event_frame(
                "done", session_id, request_id, seq.next(),
                {"status": "success", "roundIdx": round_idx},
            ))

        ai_text = "".join(ai_text_parts).strip() or "(no text output)"
        stores.complete_round(session_id, round_idx, ai_text, trajectory=trajectory)
        yield terminal_frame

    async def _stream_chat(
        self,
        session_id: str,
        task_id: str,
        user_message: str,
        history: List[Dict[str, str]],
    ):
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()
        stop_event = threading.Event()

        store_dir = str(stores.business_store_dir(session_id))

        def offer(item) -> None:
            if not stop_event.is_set():
                queue.put_nowait(item)

        def worker():
            source = None
            try:
                source = run_chat_agent(
                    session_id, task_id, user_message, history,
                    store_dir=store_dir,
                )
                iterator = iter(source)
                while not stop_event.is_set():
                    try:
                        ev = next(iterator)
                    except StopIteration:
                        break
                    if stop_event.is_set():
                        break
                    loop.call_soon_threadsafe(offer, ev)
            except Exception as exc:  # noqa: BLE001
                if not stop_event.is_set():
                    loop.call_soon_threadsafe(offer, ("__error__", exc))
            finally:
                close = getattr(source, "close", None)
                if close is not None:
                    try:
                        close()
                    except Exception:
                        pass
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


def _chat_frame(frame: Dict[str, Any]) -> Dict[str, Any]:
    frame["data_type"] = "chat.event"
    return frame
