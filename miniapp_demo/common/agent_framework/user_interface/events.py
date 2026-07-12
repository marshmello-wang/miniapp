"""
事件定义 - 定义 Agent 输出的事件流结构
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from time import time
from .content_blocks import ContentBlock


@dataclass
class Event:
    """
    通用事件类
    
    event_type 由具体的 agent loop 决定，例如：
    - "reasoning_start" / "reasoning_complete"
    - "tool_call" / "tool_result"
    - "planning" / "reflection"
    - "task_complete" / "error"
    
    user_interface 协议层不预设具体的事件类型，保持通用性
    
    session_id: 会话 ID，同一 session 下的多个 task 可以复用 KV cache
    task_id: 任务 ID，唯一标识一个任务
    """
    event_id: str
    session_id: str
    task_id: str
    event_type: str  # 事件类型，由 agent loop 自定义
    content: List[ContentBlock]  # 事件携带的内容块列表
    timestamp: float = field(default_factory=time)
    metadata: Optional[Dict[str, Any]] = None  # 额外的元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "event_type": self.event_type,
            "content": [block.to_dict() for block in self.content],
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }
    
    @classmethod
    def create(
        cls,
        event_id: str,
        session_id: str,
        task_id: str,
        event_type: str,
        content: List[ContentBlock],
        metadata: Optional[Dict[str, Any]] = None
    ) -> "Event":
        """创建事件的便捷方法"""
        return cls(
            event_id=event_id,
            session_id=session_id,
            task_id=task_id,
            event_type=event_type,
            content=content,
            metadata=metadata
        )

