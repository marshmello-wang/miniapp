"""app-skill v0.3 协议:帧构造 + agent_framework Event/ContentBlock -> app.event 转换。

下行:
- app.resource : 挂载(仅资源)
- app.event    : 一次 action 的事件流,type ∈ thinking|text|tool_call|tool_result|ui_update|done
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, Iterator, List, Optional

from common.agent_framework.user_interface.content_blocks import (
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
)

APP_EMIT_TOOL = "app_emit"


def make_resource_frame(
    app_session: str,
    manifest_dict: Dict[str, Any],
    ui_url: str,
    on_init: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    app_info: Dict[str, Any] = {
        "id": manifest_dict["id"],
        "name": manifest_dict["name"],
        "version": manifest_dict["version"],
    }
    if on_init:
        app_info["on_init"] = on_init
    return {
        "data_type": "app.resource",
        "data": {
            "appSession": app_session,
            "app": app_info,
            "resource": {"uri": ui_url, "mimeType": "text/html;profile=app-skill"},
        },
    }


def make_event_frame(
    event_type: str,
    app_session: str,
    request_id: str,
    seq: int,
    payload: Dict[str, Any],
    app_id: Optional[str] = None,
) -> Dict[str, Any]:
    data = {
        "type": event_type,
        "appSession": app_session,
        "requestId": request_id,
        "seq": seq,
        "ts": time.time(),
        "payload": payload,
    }
    if app_id is not None:
        data["appId"] = app_id
    return {
        "data_type": "app.event",
        "data": data,
    }


_UI_EVENT_TYPES = frozenset(("reasoning", "tool_result", "task_complete", "error", "warning"))


def _blocks_to_partials(agent_event) -> List[Dict[str, Any]]:
    """把一个 agent Event 转成若干 {type, payload} 片段(未编号)。
    只处理白名单内的 event_type,框架内部事件(orchestration_*/node_*)直接丢弃。
    """
    et = agent_event.event_type
    if et not in _UI_EVENT_TYPES:
        return []
    out: List[Dict[str, Any]] = []

    if et in ("reasoning", "tool_result"):
        for block in agent_event.content:
            if isinstance(block, ThinkingBlock):
                out.append({"type": "thinking", "payload": {"delta": block.thinking, "final": True}})
            elif isinstance(block, TextBlock):
                out.append({"type": "text", "payload": {"delta": block.text, "final": True}})
            elif isinstance(block, ToolCallBlock):
                if block.tool_name == APP_EMIT_TOOL:
                    data = block.tool_input or {}
                    structured = data.get("structuredContent", data)
                    out.append({"type": "ui_update", "payload": {"structuredContent": structured}})
                else:
                    out.append({
                        "type": "tool_call",
                        "payload": {
                            "callId": block.call_id,
                            "name": block.tool_name,
                            "arguments": block.tool_input,
                        },
                    })
            elif isinstance(block, ToolResultBlock):
                if block.tool_name == APP_EMIT_TOOL:
                    continue  # ui_update 已在 tool_call 时产出
                result = block.result
                summary = result if isinstance(result, str) else str(result)
                out.append({
                    "type": "tool_result",
                    "payload": {
                        "callId": block.call_id,
                        "name": block.tool_name,
                        "resultSummary": summary[:800],
                        "isError": block.is_error,
                    },
                })
                if block.tool_name == "bash":
                    event_metadata = agent_event.metadata or {}
                    tool_metadata = event_metadata.get("metadata") or {}
                    miniapp_metadata = tool_metadata.get("miniapp") or {}
                    for structured in miniapp_metadata.get("uiUpdates") or []:
                        out.append({
                            "type": "ui_update",
                            "payload": {"structuredContent": structured},
                        })
    elif et == "task_complete":
        out.append({"type": "done", "payload": {"status": "success"}})
    elif et in ("error", "warning"):
        text = ""
        for block in agent_event.content:
            if isinstance(block, TextBlock):
                text += block.text
        if text:
            out.append({"type": "text", "payload": {"delta": text, "final": True}})
        if et == "error":
            out.append({"type": "done", "payload": {"status": "error", "error": text or "agent error"}})

    return out


class SeqCounter:
    def __init__(self, start: int = 0):
        self._n = start

    def next(self) -> int:
        n = self._n
        self._n += 1
        return n


def frames_for_event(
    agent_event,
    app_session: str,
    request_id: str,
    seq: SeqCounter,
    app_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """把单个 agent Event 转成若干 app.event 帧(已编号)。"""
    return [
        make_event_frame(
            p["type"],
            app_session,
            request_id,
            seq.next(),
            p["payload"],
            app_id=app_id,
        )
        for p in _blocks_to_partials(agent_event)
    ]


def agent_events_to_app_events(
    agent_events: Iterable,
    app_session: str,
    request_id: str,
    seq: SeqCounter,
    app_id: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    """把 agent 事件流转成 app.event 帧流(边转边 yield)。不保证一定含 done,由调用方兜底。"""
    for ev in agent_events:
        for frame in frames_for_event(
            ev,
            app_session,
            request_id,
            seq,
            app_id=app_id,
        ):
            yield frame
