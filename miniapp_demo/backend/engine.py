"""MiniAppEngine:小程序引擎。

职责:
- enter_app:每(用户,小程序)get-or-create 一个 session,返回挂载资源帧。
- direct_action:走 sandbox 执行脚本 -> ui_update -> done,并把交互记入历史。
- agent_action:读历史 + 注入 env,跑真 LLM agent,逐 Event 流式转 app.event。
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from common.agent_framework.user_interface.content_blocks import TextBlock

from . import protocol, sandbox, stores
from .agent_runner import run_agent
from .app_registry import AppManifest, get_app


class MiniAppEngine:
    def __init__(self, user: str = "local"):
        self.user = user

    # -------------------------------------------------- enter
    def enter_app(
        self, app_id: str, session_id_override: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        manifest = get_app(app_id)
        if manifest is None:
            return None
        session_id = session_id_override or stores.get_or_create_session(self.user, manifest)
        ui_url = f"/api/apps/{app_id}/ui/{Path(manifest.entry_ui).name}"

        on_init = None
        if manifest.on_init and manifest.on_init.user_message:
            first_visit = not stores.has_app_rounds(session_id, app_id)
            if first_visit:
                on_init = {"user_message": manifest.on_init.user_message}

        resource = protocol.make_resource_frame(
            session_id, manifest.to_dict(), ui_url, on_init=on_init,
        )
        return {"session_id": session_id, "manifest": manifest.to_dict(), "resource": resource}

    # -------------------------------------------------- direct_action
    async def direct_action(
        self,
        app_id: str,
        name: str,
        args: Dict[str, Any],
        request_id: str,
        session_id_override: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        manifest = get_app(app_id)
        seq = protocol.SeqCounter()
        if manifest is None:
            yield protocol.make_event_frame("done", "", request_id, seq.next(),
                                            {"status": "error", "error": "app not found"})
            return

        session_id = session_id_override or stores.get_or_create_session(self.user, manifest)
        store_dir = stores.business_store_dir(session_id)
        script = manifest.script_by_name(name)
        if script is None or "ui" not in script.visibility:
            yield protocol.make_event_frame("done", session_id, request_id, seq.next(),
                                            {"status": "error", "error": f"unknown action: {name}"})
            return

        result = await sandbox.run_script(
            manifest.root / script.path, manifest.root, store_dir, args
        )
        yield protocol.make_event_frame(
            "ui_update", session_id, request_id, seq.next(),
            {"structuredContent": result.structured_content},
        )
        summary = json.dumps(result.structured_content, ensure_ascii=False)[:400]
        stores.append_app_action(session_id, name, args, summary)
        yield protocol.make_event_frame(
            "done", session_id, request_id, seq.next(),
            {"status": "success" if result.ok else "error"},
        )

    # -------------------------------------------------- agent_action
    async def agent_action(
        self,
        app_id: str,
        intent: str,
        focus: Optional[Dict[str, Any]],
        env: Optional[Dict[str, Any]],
        request_id: str,
        session_id_override: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        manifest = get_app(app_id)
        seq = protocol.SeqCounter()
        if manifest is None:
            yield protocol.make_event_frame("done", "", request_id, seq.next(),
                                            {"status": "error", "error": "app not found"})
            return

        session_id = session_id_override or stores.get_or_create_session(self.user, manifest)
        store_dir = stores.business_store_dir(session_id)
        history = stores.load_history_rich(session_id)

        user_message = _compose_prompt(intent, focus, env)
        source = f"miniapp:{app_id}" if session_id_override else "chat"
        round_idx = stores.start_round(session_id, intent or "(agent_action)", source=source)

        task_id = f"task_{uuid4().hex[:12]}"
        trajectory: List[Dict[str, Any]] = []
        ai_text_parts: List[str] = []
        saw_done = False
        error_text: Optional[str] = None

        _INTERNAL_EVENTS = frozenset((
            "orchestration_start", "orchestration_complete",
            "node_start", "node_complete",
        ))

        async for item in self._stream_agent(
            manifest, store_dir, session_id, task_id, user_message, history
        ):
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
            ui_frames = [f for f in frames if f["data"]["type"] == "ui_update"]
            other_frames = [f for f in frames if f["data"]["type"] != "ui_update"]
            for frame in ui_frames:
                yield frame
            if ui_frames and other_frames:
                await asyncio.sleep(0.05)
            for frame in other_frames:
                if frame["data"]["type"] == "done":
                    saw_done = True
                yield frame

        if error_text is not None:
            yield protocol.make_event_frame("text", session_id, request_id, seq.next(),
                                            {"delta": f"[agent error] {error_text}", "final": True})
            yield protocol.make_event_frame("done", session_id, request_id, seq.next(),
                                            {"status": "error", "error": error_text})
            saw_done = True
        elif not saw_done:
            yield protocol.make_event_frame("done", session_id, request_id, seq.next(),
                                            {"status": "success"})

        ai_text = "".join(ai_text_parts).strip() or "(no text output)"
        stores.complete_round(session_id, round_idx, ai_text, trajectory=trajectory)

    async def _stream_agent(
        self,
        manifest: AppManifest,
        store_dir: Path,
        session_id: str,
        task_id: str,
        user_message: str,
        history: List[Dict[str, Any]],
    ):
        """在线程里跑同步的 agent 生成器,通过队列桥接到 asyncio(真流式)。"""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        def worker():
            try:
                for ev in run_agent(
                    manifest, store_dir, session_id, task_id, user_message, history
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


def _compose_prompt(
    intent: str,
    focus: Optional[Dict[str, Any]],
    env: Optional[Dict[str, Any]],
) -> str:
    parts: List[str] = []
    if env:
        parts.append("[界面当前状态 env]\n" + json.dumps(env, ensure_ascii=False, indent=2))
    if focus:
        parts.append("[用户聚焦 focus]\n" + json.dumps(focus, ensure_ascii=False, indent=2))
    parts.append("[用户意图]\n" + (intent or ""))
    return "\n\n".join(parts)
