"""存储层:
- Agent 消息存储:复用 agent_framework 的 MessageStore(sqlite, ~/.miniapp/messages.db)。
- Sandbox 业务 store:每个 session 一个目录,仅脚本读写,初始内容由 skill 的 assets/schema 定义。
- 会话:每(用户, 小程序)一个 session,get-or-create。
- Chat 会话:每用户可创建多个 chat session,session_id 格式 {username}__chat__{uuid}。
"""
from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from common.agent_framework.message_store.store import MessageStore

from . import config
from .app_registry import AppManifest

_store: Optional[MessageStore] = None
_lock = threading.RLock()


def get_store() -> MessageStore:
    global _store
    if _store is None:
        config.ensure_directories()
        _store = MessageStore(str(config.MESSAGES_DB))
    return _store


def session_id_for(user: str, app_id: str) -> str:
    return f"{user}__{app_id}"


# ================================================================
# Chat Session 管理
# ================================================================

def create_chat_session(username: str, title: str = "") -> Dict[str, Any]:
    """创建一个 chat session,返回 {session_id, title, created_at}。"""
    store = get_store()
    sid = f"{username}__chat__{uuid4().hex[:12]}"
    now = time.time()
    with _lock:
        store.create_session(username, session_id=sid)
        meta = {"title": title or "新对话", "type": "chat"}
        store._set_metadata(sid, meta)
    return {"session_id": sid, "title": title or "新对话", "created_at": now}


def list_chat_sessions(username: str) -> List[Dict[str, Any]]:
    """列出用户所有 chat session,按更新时间倒序。"""
    store = get_store()
    with _lock:
        sessions = store.list_sessions(username)
    result = []
    for s in sessions:
        if "__chat__" not in s.session_id:
            continue
        meta = s.metadata or {}
        result.append({
            "session_id": s.session_id,
            "title": meta.get("title", "新对话"),
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "round_count": s.round_count,
        })
    return result


def delete_chat_session(session_id: str) -> None:
    """删除 chat session 的消息和 session 记录。"""
    store = get_store()
    with _lock:
        store.clear_rounds(session_id)
        store._conn.execute(
            "DELETE FROM sessions WHERE session_id = ?", (session_id,)
        )
        store._conn.commit()


def load_chat_history(session_id: str) -> List[Dict[str, Any]]:
    """加载 chat 历史用于 UI 展示。

    - chat 来源的轮次正常展示为 user/assistant 消息。
    - 连续的同一 miniapp 来源的轮次合并为一个折叠摘要条目。
    """
    store = get_store()
    with _lock:
        rounds = store.get_rounds(session_id)
    history: List[Dict[str, Any]] = []

    pending_app: Optional[str] = None
    pending_count = 0
    pending_last_ai = ""

    def flush_miniapp():
        nonlocal pending_app, pending_count, pending_last_ai
        if pending_app:
            history.append({
                "role": "miniapp",
                "appId": pending_app,
                "rounds": pending_count,
                "summary": pending_last_ai[:120] if pending_last_ai else "",
            })
            pending_app = None
            pending_count = 0
            pending_last_ai = ""

    for rnd in rounds:
        if not rnd.user_content:
            continue
        source = rnd.user_content[0].get("source", "chat") if rnd.user_content else "chat"

        if source.startswith("miniapp:"):
            app_id = source.split(":", 1)[1]
            if pending_app and pending_app != app_id:
                flush_miniapp()
            pending_app = app_id
            pending_count += 1
            ai_text = _content_to_text(rnd.ai_content)
            if ai_text:
                pending_last_ai = ai_text
            continue

        flush_miniapp()
        user_text = _content_to_text(rnd.user_content)
        if user_text:
            history.append({"role": "user", "content": user_text})
        if rnd.ai_content:
            ai_text = _content_to_text(rnd.ai_content)
            if ai_text:
                history.append({"role": "assistant", "content": ai_text, "roundIdx": rnd.round_idx})

    flush_miniapp()
    return history


def update_chat_session_title(session_id: str, title: str) -> None:
    """更新 chat session 标题。"""
    store = get_store()
    with _lock:
        meta = store._get_metadata(session_id)
        meta["title"] = title
        store._set_metadata(session_id, meta)


def get_round_debug(session_id: str, round_idx: int) -> Optional[Dict[str, Any]]:
    """获取某轮对话的调试信息: 输入历史(含 trajectory) + 用户输入 + 轨迹。"""
    store = get_store()
    with _lock:
        rnd = store.get_round(session_id, round_idx)
        if rnd is None:
            return None
        all_rounds = store.get_rounds(session_id)

    input_history: List[Dict[str, Any]] = []
    for r in all_rounds:
        if r.round_idx >= round_idx:
            break
        source = "chat"
        if r.user_content:
            source = r.user_content[0].get("source", "chat")
        user_text = _content_to_text(r.user_content)
        if user_text:
            input_history.append({"role": "user", "content": user_text, "source": source})
        if r.ai_content:
            ai_text = _content_to_text(r.ai_content)
            if ai_text:
                input_history.append({"role": "assistant", "content": ai_text, "source": source})

    return {
        "round_idx": round_idx,
        "user_input": _content_to_text(rnd.user_content),
        "ai_output": _content_to_text(rnd.ai_content),
        "input_history": input_history,
        "trajectory": rnd.trajectory or [],
    }


def business_store_dir(session_id: str) -> Path:
    return config.SESSIONS_DIR / session_id


def get_or_create_session(user: str, manifest: AppManifest) -> str:
    """每(用户, 小程序)一个 session;不存在则创建并初始化业务 store。"""
    store = get_store()
    sid = session_id_for(user, manifest.id)
    with _lock:
        if store.get_session(sid) is None:
            store.create_session(user, session_id=sid)
        _init_business_store(sid, manifest)
    return sid


def _init_business_store(session_id: str, manifest: AppManifest) -> None:
    """首次进入时,把 skill 的 assets/schema/* 拷进业务 store 目录作为初始数据。"""
    dst = business_store_dir(session_id)
    if dst.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    schema_dir = manifest.root / "assets" / "schema"
    if schema_dir.is_dir():
        for item in schema_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, dst / item.name)


def reset_session(user: str, manifest: AppManifest) -> str:
    """清空 session 的全部历史消息并重置 business store。"""
    store = get_store()
    sid = session_id_for(user, manifest.id)
    with _lock:
        store.clear_rounds(sid)
        dst = business_store_dir(sid)
        if dst.exists():
            shutil.rmtree(dst)
        _init_business_store(sid, manifest)
    return sid


def append_app_action(
    session_id: str,
    name: str,
    arguments: Dict[str, Any],
    result_summary: str,
) -> None:
    """把一次 direct_action 作为最小交互记录写入会话历史,供后续 agent 读回。"""
    store = get_store()
    with _lock:
        idx = store.start_round(
            session_id,
            [{"type": "text", "content": f"[direct_action] {name} args={json.dumps(arguments, ensure_ascii=False)}"}],
        )
        store.complete_round(
            session_id,
            idx,
            [{"type": "text", "content": f"[direct_action result] {result_summary}"}],
        )


def load_history(session_id: str) -> List[Dict[str, str]]:
    """把已完成的 round 转成 [{role, content}] 供 agent 作为历史上下文。"""
    store = get_store()
    with _lock:
        rounds = store.get_rounds(session_id)
    history: List[Dict[str, str]] = []
    for rnd in rounds:
        user_text = _content_to_text(rnd.user_content)
        if user_text:
            history.append({"role": "user", "content": user_text})
        if rnd.ai_content:
            ai_text = _content_to_text(rnd.ai_content)
            if ai_text:
                history.append({"role": "assistant", "content": ai_text})
    return history


def start_round(session_id: str, user_text: str, source: str = "chat") -> int:
    store = get_store()
    with _lock:
        return store.start_round(
            session_id,
            [{"type": "text", "content": user_text, "source": source}],
        )


def complete_round(
    session_id: str,
    round_idx: int,
    ai_text: str,
    trajectory: Optional[List[Dict[str, Any]]] = None,
) -> None:
    store = get_store()
    with _lock:
        store.complete_round(
            session_id,
            round_idx,
            [{"type": "text", "content": ai_text}],
            trajectory=trajectory,
        )


def load_history_rich(session_id: str) -> List[Dict[str, Any]]:
    """把已完成的 round 转成标准 LLM API 消息格式，含 tool call/result。

    返回的消息列表包含三种角色:
    - {"role": "user", "content": "..."}
    - {"role": "assistant", "content": "...", "tool_calls": [{"id":..,"name":..,"arguments":..}]}
    - {"role": "tool", "tool_call_id": "...", "name": "...", "content": "..."}
    """
    store = get_store()
    with _lock:
        rounds = store.get_rounds(session_id)
    history: List[Dict[str, Any]] = []
    for rnd in rounds:
        user_text = _content_to_text(rnd.user_content)
        if user_text:
            history.append({"role": "user", "content": user_text})
        if rnd.trajectory:
            history.extend(_trajectory_to_messages(rnd.trajectory))
        elif rnd.ai_content:
            ai_text = _content_to_text(rnd.ai_content)
            if ai_text:
                history.append({"role": "assistant", "content": ai_text})
    return history


def _trajectory_to_messages(trajectory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从 trajectory 重建标准 LLM API 格式的 assistant / tool 消息序列。

    逻辑与 DefaultContextStrategy._process_events() 一致:
    reasoning event 累积 text + tool_calls，遇到 tool_result 时先 flush assistant 再追加 tool。
    """
    messages: List[Dict[str, Any]] = []
    pending_text: Optional[str] = None
    pending_tool_calls: List[Dict[str, Any]] = []

    def _flush():
        nonlocal pending_text, pending_tool_calls
        if pending_text is not None or pending_tool_calls:
            msg: Dict[str, Any] = {"role": "assistant", "content": pending_text or ""}
            if pending_tool_calls:
                msg["tool_calls"] = pending_tool_calls
            messages.append(msg)
            pending_text = None
            pending_tool_calls = []

    for ev in trajectory:
        etype = ev.get("event_type", "")

        if etype in ("reasoning_complete", "reasoning"):
            texts: List[str] = []
            for block in ev.get("content", []):
                btype = block.get("type", "")
                if btype == "text":
                    t = block.get("text", "")
                    if t:
                        texts.append(t)
                elif btype == "tool_call":
                    pending_tool_calls.append({
                        "id": block.get("call_id") or "",
                        "name": block.get("tool_name", ""),
                        "arguments": block.get("tool_input", {}),
                    })
            if texts:
                pending_text = "\n".join(texts)

        elif etype == "tool_result":
            _flush()
            for block in ev.get("content", []):
                if block.get("type") == "tool_result":
                    result = block.get("result", "")
                    if block.get("is_error") and block.get("error_message"):
                        result = f"Error: {block['error_message']}"
                    if not isinstance(result, str):
                        result = json.dumps(result, ensure_ascii=False)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": block.get("call_id") or "",
                        "name": block.get("tool_name", ""),
                        "content": result,
                    })

    _flush()
    return messages


def _content_to_text(content: Optional[List[Dict[str, Any]]]) -> str:
    if not content:
        return ""
    parts = []
    for item in content:
        if item.get("type") == "text" and item.get("content"):
            parts.append(item["content"])
    return "\n".join(parts)


def _extract_tool_events(trajectory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从 trajectory 中提取 tool_call / tool_result 事件摘要,供 debug 历史展示。"""
    _TOOL_TYPES = {"tool_call", "tool_result"}
    out: List[Dict[str, Any]] = []
    for ev in trajectory:
        contents = ev.get("content", [])
        for block in contents:
            btype = block.get("type", "")
            if btype == "tool_call":
                out.append({
                    "type": "tool_call",
                    "name": block.get("tool_name", ""),
                    "arguments": block.get("tool_input", {}),
                })
            elif btype == "tool_result":
                result = block.get("result", "")
                if isinstance(result, str) and len(result) > 500:
                    result = result[:500] + "…"
                out.append({
                    "type": "tool_result",
                    "name": block.get("tool_name", ""),
                    "result": result,
                    "is_error": block.get("is_error", False),
                })
    return out
