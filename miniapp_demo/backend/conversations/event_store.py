"""SQLite-backed durable conversation event log."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_EVENT_COLUMNS = (
    "event_id",
    "conversation_id",
    "conversation_seq",
    "action_id",
    "parent_event_id",
    "skill_id",
    "ui_instance_id",
    "tool_call_id",
    "actor",
    "event_type",
    "ts",
    "payload_json",
)


class EventStore:
    def __init__(self, root_dir: Path):
        self._root_dir = Path(root_dir)
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _db_path(self, conversation_id: str) -> Path:
        safe = conversation_id.replace("/", "_")
        conv_dir = self._root_dir / safe
        conv_dir.mkdir(parents=True, exist_ok=True)
        return conv_dir / "events.db"

    def _connect(self, conversation_id: str) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path(conversation_id)))
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_events (
                event_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                conversation_seq INTEGER NOT NULL,
                action_id TEXT,
                parent_event_id TEXT,
                skill_id TEXT,
                ui_instance_id TEXT,
                tool_call_id TEXT,
                actor TEXT NOT NULL,
                event_type TEXT NOT NULL,
                ts REAL NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(conversation_id, conversation_seq)
            )
            """
        )
        conn.commit()
        return conn

    def append(self, event: Dict[str, Any]) -> int:
        conversation_id = event["conversationId"]
        with self._lock:
            conn = self._connect(conversation_id)
            try:
                row = conn.execute(
                    "SELECT COALESCE(MAX(conversation_seq), 0) AS max_seq "
                    "FROM conversation_events WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()
                seq = int(row["max_seq"]) + 1
                conn.execute(
                    """
                    INSERT INTO conversation_events (
                        event_id, conversation_id, conversation_seq,
                        action_id, parent_event_id, skill_id, ui_instance_id,
                        tool_call_id, actor, event_type, ts, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["eventId"],
                        conversation_id,
                        seq,
                        event.get("actionId"),
                        event.get("parentEventId"),
                        event.get("skillId"),
                        event.get("uiInstanceId"),
                        event.get("toolCallId"),
                        event["actor"],
                        event["type"],
                        float(event["ts"]),
                        json.dumps(event.get("payload") or {}, ensure_ascii=False),
                    ),
                )
                conn.commit()
                return seq
            finally:
                conn.close()

    def replay(
        self,
        conversation_id: str,
        *,
        after: int = 0,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            if not self._db_path(conversation_id).exists():
                return []
            conn = self._connect(conversation_id)
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM conversation_events
                    WHERE conversation_id = ? AND conversation_seq > ?
                    ORDER BY conversation_seq ASC
                    """,
                    (conversation_id, after),
                ).fetchall()
                return [self._row_to_event(row) for row in rows]
            finally:
                conn.close()

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Dict[str, Any]:
        event: Dict[str, Any] = {
            "eventId": row["event_id"],
            "conversationId": row["conversation_id"],
            "conversationSeq": row["conversation_seq"],
            "actor": row["actor"],
            "type": row["event_type"],
            "ts": row["ts"],
            "payload": json.loads(row["payload_json"]),
        }
        if row["action_id"]:
            event["actionId"] = row["action_id"]
        if row["parent_event_id"]:
            event["parentEventId"] = row["parent_event_id"]
        if row["skill_id"]:
            event["skillId"] = row["skill_id"]
        if row["ui_instance_id"]:
            event["uiInstanceId"] = row["ui_instance_id"]
        if row["tool_call_id"]:
            event["toolCallId"] = row["tool_call_id"]
        return event
