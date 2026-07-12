"""
User Interface - Agent 框架的通用输入输出协议
"""

# 输入类型
from .inputs import (
    ImageContent,
    VideoContent,
    MessageContent,
    Message,
    AgentConfig,
    TaskInput,
)

# 内容块
from .content_blocks import (
    ContentBlock,
    TextBlock,
    ImageBlock,
    VideoBlock,
    ToolCallBlock,
    ToolResultBlock,
    ThinkingBlock,
    StructuredDataBlock,
)

# 事件
from .events import Event

# 协议接口
from .protocol import Agent

__all__ = [
    # 输入类型
    "ImageContent",
    "VideoContent",
    "MessageContent",
    "Message",
    "AgentConfig",
    "TaskInput",
    # 内容块
    "ContentBlock",
    "TextBlock",
    "ImageBlock",
    "VideoBlock",
    "ToolCallBlock",
    "ToolResultBlock",
    "ThinkingBlock",
    "StructuredDataBlock",
    # 事件
    "Event",
    # 协议
    "Agent",
]

