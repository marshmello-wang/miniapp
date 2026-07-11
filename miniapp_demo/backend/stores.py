"""存储层:
- Agent 消息存储:复用 agent_framework 的 MessageStore(sqlite, ~/.miniapp/messages.db)。
- Sandbox 业务 store:每个 session 一个目录,仅脚本读写,初始内容由 skill 的 assets/schema 定义。
- 会话:每(用户, 小程序)一个 session,get-or-create。
"""
from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def start_round(session_id: str, user_text: str) -> int:
    store = get_store()
    with _lock:
        return store.start_round(session_id, [{"type": "text", "content": user_text}])


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


def _content_to_text(content: Optional[List[Dict[str, Any]]]) -> str:
    if not content:
        return ""
    parts = []
    for item in content:
        if item.get("type") == "text" and item.get("content"):
            parts.append(item["content"])
    return "\n".join(parts)
