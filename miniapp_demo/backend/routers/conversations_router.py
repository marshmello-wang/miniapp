"""Conversation Command + SSE API."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import config
from ..conversations.agent_lane import DuplicateActionError
from ..conversations.event_store import EventStore
from ..conversations.runtime import ConversationRuntime

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_event_root = config.MINIAPP_HOME / "conversations"
_event_root.mkdir(parents=True, exist_ok=True)
_event_store = EventStore(_event_root)
_runtime = ConversationRuntime(_event_store)

_REQUIRED = ("actionId", "conversationId", "kind", "source")


@router.post("/{conversation_id}/actions")
async def submit_action(conversation_id: str, body: Dict[str, Any] = Body(...)):
    payload = dict(body)
    payload["conversationId"] = conversation_id
    missing = [field for field in _REQUIRED if not payload.get(field)]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"missing required field(s): {', '.join(missing)}",
        )
    if payload["kind"] not in ("agent", "direct"):
        raise HTTPException(status_code=422, detail="kind must be agent or direct")
    if payload["source"] not in ("chat", "ui"):
        raise HTTPException(status_code=422, detail="source must be chat or ui")
    if payload["kind"] == "direct" and not payload.get("name"):
        raise HTTPException(status_code=422, detail="direct action requires name")

    try:
        return await _runtime.submit_action(payload)
    except DuplicateActionError as exc:
        raise HTTPException(status_code=409, detail=f"duplicate actionId: {exc}") from exc


@router.post("/{conversation_id}/actions/{action_id}/snapshot")
async def submit_snapshot(
    conversation_id: str,
    action_id: str,
    body: Dict[str, Any] = Body(...),
):
    try:
        return await _runtime.submit_snapshot(conversation_id, action_id, body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{conversation_id}/actions/{action_id}/cancel")
async def cancel_action(conversation_id: str, action_id: str):
    cancelled = await _runtime.cancel_action(conversation_id, action_id)
    return {"conversationId": conversation_id, "actionId": action_id, "cancelled": cancelled}


@router.get("/{conversation_id}/events")
async def stream_events(
    conversation_id: str,
    after: int = Query(0, ge=0),
):
    async def encode_sse():
        async for event in _runtime.subscribe(conversation_id, after=after):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        encode_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
