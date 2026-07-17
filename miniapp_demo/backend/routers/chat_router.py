"""Chat session 管理 REST API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import stores
from ..chat_agent_runner import get_chat_system_prompt
from ..chat_engine import _HISTORY_TOOL_WHITELIST

router = APIRouter(prefix="/api/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    username: str
    title: str = ""


@router.post("/sessions")
def create_session(req: CreateSessionRequest):
    return stores.create_chat_session(req.username, req.title)


@router.get("/sessions")
def list_sessions(username: str):
    return stores.list_chat_sessions(username)


@router.get("/sessions/{session_id}/history")
def get_history(session_id: str):
    return stores.load_chat_history(session_id)


@router.get("/sessions/{session_id}/rounds/{round_idx}/debug")
def get_round_debug(session_id: str, round_idx: int):
    debug = stores.get_round_debug(
        session_id, round_idx, tool_whitelist=_HISTORY_TOOL_WHITELIST
    )
    if debug is None:
        raise HTTPException(404, "round not found")
    debug["system_prompt"] = get_chat_system_prompt()
    return debug


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    stores.delete_chat_session(session_id)
    return {"ok": True}
