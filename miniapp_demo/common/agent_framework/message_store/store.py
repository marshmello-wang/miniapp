"""
MessageStore - SQLite 消息存储主类

提供 user / session / round / user_memory 的全部 CRUD。
每个 round = 一次用户交互轮次（用户输入 + AI 回复 + agent 执行轨迹）。
session 级 KV 存储（expire content 等）合并在 sessions.metadata JSON 中。
"""
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import Round, SessionInfo, UserMemory
from .schema import init_db


class MessageStore:
    """
    基于 SQLite 的消息存储

    层次结构: user -> session -> round
    每个 round 包含:
      - user_content: 用户输入 [{"type":"text|image|video","content":"..."}]
      - ai_content:   AI 回复（同格式）
      - trajectory:   agent loop 完整执行轨迹 (Event 列表)
    附加存储: session metadata (session 级 KV), user_memory (跨 session 结构化记忆)
    """

    def __init__(self, db_path: str = "messages.db"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        init_db(self._conn)

    def close(self) -> None:
        self._conn.close()

    # ================================================================
    # User
    # ================================================================

    def ensure_user(self, user_id: str) -> None:
        """确保用户存在，不存在则创建"""
        self._conn.execute(
            "INSERT OR IGNORE INTO users (user_id, created_at) VALUES (?, ?)",
            (user_id, time.time()),
        )
        self._conn.commit()

    def list_users(self) -> List[str]:
        rows = self._conn.execute(
            "SELECT user_id FROM users ORDER BY created_at"
        ).fetchall()
        return [r["user_id"] for r in rows]

    # ================================================================
    # Session
    # ================================================================

    def create_session(
        self, user_id: str, session_id: Optional[str] = None
    ) -> str:
        """创建新 session，自动 ensure_user"""
        self.ensure_user(user_id)
        sid = session_id or f"sess_{uuid4().hex[:12]}"
        now = time.time()
        self._conn.execute(
            "INSERT INTO sessions (session_id, user_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (sid, user_id, now, now),
        )
        self._conn.commit()
        return sid

    def list_sessions(self, user_id: str) -> List[SessionInfo]:
        rows = self._conn.execute(
            "SELECT s.*, COUNT(m.id) as rnd_count "
            "FROM sessions s LEFT JOIN messages m ON s.session_id = m.session_id "
            "WHERE s.user_id = ? GROUP BY s.session_id ORDER BY s.updated_at DESC",
            (user_id,),
        ).fetchall()
        return [
            SessionInfo(
                session_id=r["session_id"],
                user_id=r["user_id"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                metadata=json.loads(r["metadata"] or "{}"),
                round_count=r["rnd_count"],
            )
            for r in rows
        ]

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        r = self._conn.execute(
            "SELECT s.*, COUNT(m.id) as rnd_count "
            "FROM sessions s LEFT JOIN messages m ON s.session_id = m.session_id "
            "WHERE s.session_id = ? GROUP BY s.session_id",
            (session_id,),
        ).fetchone()
        if not r:
            return None
        return SessionInfo(
            session_id=r["session_id"],
            user_id=r["user_id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            metadata=json.loads(r["metadata"] or "{}"),
            round_count=r["rnd_count"],
        )

    # ================================================================
    # Rounds (展现层消息 + 执行轨迹)
    # ================================================================

    def start_round(
        self, session_id: str, user_content: List[Dict[str, Any]]
    ) -> int:
        """
        用户发送消息，创建新轮次

        Args:
            session_id: session ID
            user_content: [{"type":"text|image|video","content":"..."}]

        Returns:
            新轮次的 round_idx
        """
        now = time.time()

        row = self._conn.execute(
            "SELECT MAX(round_idx) as max_round FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        round_idx = (row["max_round"] + 1) if row["max_round"] is not None else 0

        self._conn.execute(
            "INSERT INTO messages "
            "(session_id, round_idx, user_content, ai_content, trajectory, created_at, updated_at) "
            "VALUES (?, ?, ?, NULL, NULL, ?, ?)",
            (
                session_id,
                round_idx,
                json.dumps(user_content, ensure_ascii=False),
                now,
                now,
            ),
        )
        self._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        self._conn.commit()
        return round_idx

    def complete_round(
        self,
        session_id: str,
        round_idx: int,
        ai_content: List[Dict[str, Any]],
        trajectory: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        agent 执行完毕，写入 AI 回复和执行轨迹

        Args:
            session_id: session ID
            round_idx: start_round 返回的轮次索引
            ai_content: [{"type":"text|image|video","content":"..."}]
            trajectory: Event.to_dict() 列表
        """
        now = time.time()
        traj_json = json.dumps(trajectory, ensure_ascii=False) if trajectory else None
        self._conn.execute(
            "UPDATE messages SET ai_content = ?, trajectory = ?, updated_at = ? "
            "WHERE session_id = ? AND round_idx = ?",
            (
                json.dumps(ai_content, ensure_ascii=False),
                traj_json,
                now,
                session_id,
                round_idx,
            ),
        )
        self._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        self._conn.commit()

    def get_rounds(self, session_id: str) -> List[Round]:
        """获取 session 的全部轮次"""
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY round_idx",
            (session_id,),
        ).fetchall()
        return [self._row_to_round(r) for r in rows]

    def clear_rounds(self, session_id: str) -> None:
        """删除指定 session 的全部轮次"""
        self._conn.execute(
            "DELETE FROM messages WHERE session_id = ?",
            (session_id,),
        )
        self._conn.commit()

    def get_round(self, session_id: str, round_idx: int) -> Optional[Round]:
        """获取单个轮次"""
        r = self._conn.execute(
            "SELECT * FROM messages WHERE session_id = ? AND round_idx = ?",
            (session_id, round_idx),
        ).fetchone()
        if not r:
            return None
        return self._row_to_round(r)

    # ================================================================
    # Session Store (metadata JSON 内的 KV 存储)
    # ================================================================

    def _get_metadata(self, session_id: str) -> Dict[str, Any]:
        row = self._conn.execute(
            "SELECT metadata FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return {}
        return json.loads(row["metadata"] or "{}")

    def _set_metadata(self, session_id: str, metadata: Dict[str, Any]) -> None:
        self._conn.execute(
            "UPDATE sessions SET metadata = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(metadata, ensure_ascii=False), time.time(), session_id),
        )
        self._conn.commit()

    def session_store_save(
        self,
        session_id: str,
        key: str,
        value: str,
        store_type: str = "expire",
    ) -> None:
        meta = self._get_metadata(session_id)
        ns = meta.setdefault(store_type, {})
        ns[key] = value
        self._set_metadata(session_id, meta)

    def session_store_load(
        self, session_id: str, key: str
    ) -> Optional[str]:
        meta = self._get_metadata(session_id)
        for ns in meta.values():
            if isinstance(ns, dict) and key in ns:
                return ns[key]
        return None

    def session_store_clear(
        self, session_id: str, store_type: Optional[str] = None
    ) -> None:
        meta = self._get_metadata(session_id)
        if store_type:
            meta.pop(store_type, None)
        else:
            meta.clear()
        self._set_metadata(session_id, meta)

    # ================================================================
    # Cross-session User Memory
    # ================================================================

    def get_user_memory(self, user_id: str) -> UserMemory:
        row = self._conn.execute(
            "SELECT * FROM user_memory WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return UserMemory(user_id=user_id)
        return UserMemory(
            user_id=row["user_id"],
            version=row["version"],
            data=json.loads(row["data"]),
            updated_at=row["updated_at"],
        )

    def set_user_memory(
        self, user_id: str, data: dict, version: int = 1
    ) -> None:
        self.ensure_user(user_id)
        self._conn.execute(
            "INSERT OR REPLACE INTO user_memory (user_id, version, data, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, version, json.dumps(data, ensure_ascii=False), time.time()),
        )
        self._conn.commit()

    # ================================================================
    # Internal helpers
    # ================================================================

    @staticmethod
    def _row_to_round(row: sqlite3.Row) -> Round:
        ai = json.loads(row["ai_content"]) if row["ai_content"] else None
        traj = json.loads(row["trajectory"]) if row["trajectory"] else None
        return Round(
            round_idx=row["round_idx"],
            user_content=json.loads(row["user_content"]),
            ai_content=ai,
            trajectory=traj,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
