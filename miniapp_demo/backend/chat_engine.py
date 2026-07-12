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
        saw_done = False
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
                    saw_done = True
                    frame["data"]["payload"]["roundIdx"] = round_idx
                yield frame

        if error_text is not None:
            yield _chat_frame(protocol.make_event_frame(
                "text", session_id, request_id, seq.next(),
                {"delta": f"[error] {error_text}", "final": True},
            ))
            yield _chat_frame(protocol.make_event_frame(
                "done", session_id, request_id, seq.next(),
                {"status": "error", "error": error_text, "roundIdx": round_idx},
            ))
            saw_done = True
        elif not saw_done:
            yield _chat_frame(protocol.make_event_frame(
                "done", session_id, request_id, seq.next(),
                {"status": "success", "roundIdx": round_idx},
            ))

        ai_text = "".join(ai_text_parts).strip() or "(no text output)"
        stores.complete_round(session_id, round_idx, ai_text, trajectory=trajectory)

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

        store_dir = str(stores.business_store_dir(session_id))

        def worker():
            try:
                for ev in run_chat_agent(
                    session_id, task_id, user_message, history,
                    store_dir=store_dir,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, ev)
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, ("__error__", exc))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        threading.Thread(target=worker, daemon=True).start()

        while True:
            item = await queue.get()
            if item is sentinel:
                break
            yield item


def _chat_frame(frame: Dict[str, Any]) -> Dict[str, Any]:
    frame["data_type"] = "chat.event"
    return frame
