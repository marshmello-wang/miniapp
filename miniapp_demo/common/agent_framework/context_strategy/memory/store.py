"""
过期内容外部存储 - 用于 prefix_ref 策略的内容存储与召回
"""
import hashlib
from typing import Dict, Optional, Protocol


class ExpiredContentStore(Protocol):
    """
    过期内容存储协议

    prefix_ref 折叠策略将被截断的完整内容存入此存储，
    生成 ref_id 供 read_expire_history 工具召回。
    """

    def save(self, content: str, content_type: str) -> str:
        """
        存入被折叠的内容

        Args:
            content: 被折叠的完整内容
            content_type: 内容类型，用于生成 ref_id 前缀（如 "think", "tool"）

        Returns:
            ref_id，格式为 {content_type}_{4位hash}，如 tool_a2rf
        """
        ...

    def load(self, ref_id: str) -> Optional[str]:
        """
        通过 ref_id 读取被折叠的内容

        Args:
            ref_id: save() 返回的引用 ID

        Returns:
            被折叠的完整内容，不存在时返回 None
        """
        ...


def _generate_ref_id(content: str, content_type: str) -> str:
    """生成 ref_id: {content_type}_{md5后4位}"""
    md5_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    return f"{content_type}_{md5_hash[-4:]}"


class InMemoryStore:
    """
    内存实现的过期内容存储

    适用于测试和单进程场景。生产环境应替换为持久化实现。
    """

    def __init__(self):
        self._data: Dict[str, str] = {}

    def save(self, content: str, content_type: str) -> str:
        ref_id = _generate_ref_id(content, content_type)
        # 哈希冲突时追加序号
        final_id = ref_id
        counter = 1
        while final_id in self._data and self._data[final_id] != content:
            final_id = f"{ref_id}_{counter}"
            counter += 1
        self._data[final_id] = content
        return final_id

    def load(self, ref_id: str) -> Optional[str]:
        return self._data.get(ref_id)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
