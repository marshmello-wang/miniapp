"""
Message Store - 基于 SQLite 的上游消息存储系统

层次结构: user -> session -> round
每个 round = 用户输入 + AI 回复 + agent 执行轨迹
附加存储: session metadata (session 级 KV), user_memory (跨 session 结构化记忆)
"""

from .models import Round, SessionInfo, UserMemory
from .schema import init_db
from .sqlite_expire_store import SqliteExpiredContentStore
from .store import MessageStore

__all__ = [
    "MessageStore",
    "SessionInfo",
    "Round",
    "UserMemory",
    "SqliteExpiredContentStore",
    "init_db",
]
