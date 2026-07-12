"""
SqliteExpiredContentStore - 基于 SQLite 的 ExpiredContentStore 实现

将 prefix_ref 折叠的完整内容持久化到 sessions.metadata JSON 中，
替代 InMemoryStore 实现跨进程/重启的内容保留。
"""
import hashlib
from typing import Optional

from .store import MessageStore


def _generate_ref_id(content: str, content_type: str) -> str:
    md5_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    return f"{content_type}_{md5_hash[-4:]}"


class SqliteExpiredContentStore:
    """
    实现 ExpiredContentStore 协议，委托 MessageStore 的 session metadata

    与 InMemoryStore 行为一致：save 返回 ref_id，load 按 ref_id 召回。
    数据写入 sessions.metadata JSON，store_type = 'expire' 命名空间。
    """

    def __init__(self, message_store: MessageStore, session_id: str):
        self._store = message_store
        self._session_id = session_id

    def save(self, content: str, content_type: str) -> str:
        ref_id = _generate_ref_id(content, content_type)
        final_id = ref_id
        counter = 1
        while True:
            existing = self._store.session_store_load(self._session_id, final_id)
            if existing is None or existing == content:
                break
            final_id = f"{ref_id}_{counter}"
            counter += 1
        self._store.session_store_save(
            self._session_id, final_id, content, store_type="expire"
        )
        return final_id

    def load(self, ref_id: str) -> Optional[str]:
        return self._store.session_store_load(self._session_id, ref_id)

    def clear(self) -> None:
        self._store.session_store_clear(self._session_id, store_type="expire")

    def __len__(self) -> int:
        meta = self._store._get_metadata(self._session_id)
        expire_ns = meta.get("expire", {})
        return len(expire_ns) if isinstance(expire_ns, dict) else 0
