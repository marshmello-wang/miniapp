"""Conversation durable event protocol helpers."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional
from uuid import uuid4

ACTORS = frozenset(("user", "agent", "tool", "runtime"))


def make_durable_event(
    *,
    conversation_id: str,
    event_type: str,
    actor: str,
    payload: Optional[Dict[str, Any]] = None,
    action_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    skill_id: Optional[str] = None,
    ui_instance_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    event_id: Optional[str] = None,
    ts: Optional[float] = None,
) -> Dict[str, Any]:
    if actor not in ACTORS:
        raise ValueError(f"invalid actor: {actor}")
    if not conversation_id:
        raise ValueError("conversation_id is required")
    if not event_type:
        raise ValueError("event_type is required")

    event: Dict[str, Any] = {
        "eventId": event_id or f"evt_{uuid4().hex}",
        "conversationId": conversation_id,
        "actor": actor,
        "type": event_type,
        "ts": ts if ts is not None else time.time(),
        "payload": payload or {},
    }
    if action_id is not None:
        event["actionId"] = action_id
    if parent_event_id is not None:
        event["parentEventId"] = parent_event_id
    if skill_id is not None:
        event["skillId"] = skill_id
    if ui_instance_id is not None:
        event["uiInstanceId"] = ui_instance_id
    if tool_call_id is not None:
        event["toolCallId"] = tool_call_id
    return event
