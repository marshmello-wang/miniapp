"""
SQLite schema 定义与初始化

所有表结构集中管理，通过 init_db() 在首次连接时创建。
"""
import sqlite3

SCHEMA_VERSION = 2

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS user_memory (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id),
    version INTEGER NOT NULL DEFAULT 1,
    data TEXT NOT NULL DEFAULT '{}',
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    round_idx INTEGER NOT NULL,
    user_content TEXT NOT NULL,
    ai_content TEXT,
    trajectory TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, round_idx);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, updated_at);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """初始化数据库 schema，幂等操作"""
    conn.executescript(TABLES_SQL)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("version", str(SCHEMA_VERSION)),
    )
    conn.commit()
