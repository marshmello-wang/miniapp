"""
存储层数据模型

展现层视角的消息结构，每个 Round = 一次用户交互轮次。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionInfo:
    """Session 元信息"""
    session_id: str
    user_id: str
    created_at: float
    updated_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    round_count: int = 0


@dataclass
class Round:
    """
    一个用户交互轮次

    user_content / ai_content 格式: [{"type":"text|image|video", "content":"..."}]
    trajectory: agent loop 的完整 Event 列表 (List[Event.to_dict()])
    """
    round_idx: int
    user_content: List[Dict[str, Any]] = field(default_factory=list)
    ai_content: Optional[List[Dict[str, Any]]] = None
    trajectory: Optional[List[Dict[str, Any]]] = None
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class UserMemory:
    """跨 session 的用户结构化记忆"""
    user_id: str
    version: int = 1
    data: Dict[str, Any] = field(default_factory=dict)
    updated_at: float = 0.0
