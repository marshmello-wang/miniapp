"""Map agent_framework events to conversation durable event payloads."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from common.agent_framework.user_interface.content_blocks import (
    TextBlock,
    ThinkingBlock,
    ToolCallBlock,
    ToolResultBlock,
)

from ..protocol import APP_EMIT_TOOL

_UI_EVENT_TYPES = frozenset(("reasoning", "tool_result", "task_complete", "error", "warning"))


def agent_event_to_durable(agent_event, *, action_id: str) -> List[Dict[str, Any]]:
    et = agent_event.event_type
    if et not in _UI_EVENT_TYPES:
        return []

    out: List[Dict[str, Any]] = []
    if et in ("reasoning", "tool_result"):
        for block in agent_event.content:
            if isinstance(block, ThinkingBlock):
                out.append({
                    "type": "agent.thinking",
                    "payload": {"delta": block.thinking},
                })
            elif isinstance(block, TextBlock):
                out.append({
                    "type": "agent.text",
                    "payload": {"delta": block.text},
                })
            elif isinstance(block, ToolCallBlock):
                if block.tool_name == APP_EMIT_TOOL:
                    data = block.tool_input or {}
                    structured = data.get("structuredContent", data)
                    command = structured.get("command") if isinstance(structured, dict) else None
                    # Tolerate model sending state/mode:"open" instead of command:"open"
                    if not command and isinstance(structured, dict):
                        if structured.get("state") == "open" or structured.get("mode") == "open":
                            command = "open"
                    if command in ("open", "navigate", "close", "show_content"):
                        skill_id = structured.get("skillId") or structured.get("type")
                        out.append({
                            "type": "ui.command",
                            "payload": {
                                "type": "ui_command",
                                "command": command,
                                "skillId": skill_id,
                                "route": structured.get("route"),
                                "payload": structured.get("payload", {}),
                            },
                        })
                    else:
                        out.append({
                            "type": "ui.command",
                            "payload": {
                                "type": "ui_command",
                                "command": "patch",
                                "payload": structured,
                            },
                        })
                else:
                    out.append({
                        "type": "agent.tool.called",
                        "payload": {
                            "callId": block.call_id,
                            "name": block.tool_name,
                            "arguments": block.tool_input,
                        },
                    })
            elif isinstance(block, ToolResultBlock):
                if block.tool_name == APP_EMIT_TOOL:
                    continue
                summary = block.result if isinstance(block.result, str) else str(block.result)
                out.append({
                    "type": "agent.tool.completed",
                    "payload": {
                        "callId": block.call_id,
                        "name": block.tool_name,
                        "resultSummary": summary[:800],
                        "isError": block.is_error,
                    },
                })
                event_metadata = agent_event.metadata or {}
                tool_metadata = event_metadata.get("metadata") or {}
                miniapp_metadata = tool_metadata.get("miniapp") or {}
                for structured in miniapp_metadata.get("uiUpdates") or []:
                    out.append({
                        "type": "ui.command",
                        "payload": {
                            "type": "ui_command",
                            "command": "patch",
                            "payload": structured,
                        },
                    })
                for command in miniapp_metadata.get("uiCommands") or []:
                    out.append({"type": "ui.command", "payload": command})
    elif et == "task_complete":
        out.append({"type": "agent.turn.completed", "payload": {"status": "success"}})
    elif et in ("error", "warning"):
        text = ""
        for block in agent_event.content:
            if isinstance(block, TextBlock):
                text += block.text
        if text:
            out.append({"type": "agent.text", "payload": {"delta": text}})
        if et == "error":
            out.append({
                "type": "agent.turn.failed",
                "payload": {"error": text or "agent error"},
            })
    return out
