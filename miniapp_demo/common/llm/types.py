"""
LLM 统一类型定义

定义了与 LLM 交互所需的所有数据类型，包括消息、工具、请求和响应。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union


# 统一的思考级别 ("disabled" 显式关闭模型思考能力)
ThinkingLevel = Literal["disabled", "minimal", "low", "medium", "high"]


@dataclass
class TextContent:
    """文本内容"""
    text: str
    type: str = "text"


@dataclass
class ImageContent:
    """图片内容 (base64 编码)"""
    data: str  # base64 编码的图片数据
    media_type: str  # "image/jpeg", "image/png", "image/gif", "image/webp"
    type: str = "image"


@dataclass
class VideoContent:
    """视频内容 (base64 编码)"""
    data: str  # base64 编码的视频数据
    media_type: str  # "video/mp4", "video/webm", "video/mov", "video/avi" 等
    type: str = "video"


# 内容类型可以是纯文本字符串，或者文本/图片/视频内容的列表
ContentType = Union[str, List[Union[TextContent, ImageContent, VideoContent]]]


@dataclass
class Message:
    """消息"""
    role: str  # "system" | "user" | "assistant" | "tool"
    content: ContentType
    # 用于 tool 角色的消息
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # 工具名称 (tool 角色时使用)
    # 用于 assistant 角色的消息（当模型调用工具时）
    tool_calls: Optional[List["ToolCall"]] = None
    # 用于 assistant 角色的消息（thinking/reasoning 内容）
    thinking: Optional[str] = None


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema 格式


@dataclass
class ToolChoice:
    """工具选择策略"""
    mode: str  # "auto" | "none" | "required" | "specific"
    tool_name: Optional[str] = None  # mode="specific" 时指定具体工具名


@dataclass
class ChatRequest:
    """聊天请求"""
    messages: List[Message]
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[ToolChoice] = None
    max_tokens: int = 4096
    temperature: float = 1.0
    top_p: Optional[float] = None
    stop: Optional[List[str]] = None
    thinking_level: Optional[ThinkingLevel] = None  # 思考级别: "minimal" | "low" | "medium" | "high"


@dataclass
class ToolCall:
    """工具调用"""
    id: str
    name: str
    arguments: Dict[str, Any]
    
    def __post_init__(self):
        """如果 id 为空，自动生成 UUID"""
        if not self.id:
            import uuid
            self.id = f"call_{uuid.uuid4().hex[:24]}"


@dataclass
class Usage:
    """Token 使用统计"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int = 0
    cached_tokens: int = 0

    def __post_init__(self):
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens


@dataclass
class ChatResponse:
    """聊天响应"""
    content: Optional[str] = None
    thinking: Optional[str] = None  # 思考过程 (thinking models)
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: str = "stop"  # "stop" | "tool_calls" | "length" | "content_filter"
    usage: Optional[Usage] = None
    raw_response: Optional[Dict[str, Any]] = None  # 原始响应，用于调试


class LLMError(Exception):
    """LLM 调用异常基类"""
    def __init__(self, message: str, status_code: Optional[int] = None, raw_response: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response


class AuthenticationError(LLMError):
    """认证失败"""
    pass


class RateLimitError(LLMError):
    """速率限制"""
    pass


class InvalidRequestError(LLMError):
    """无效请求"""
    pass


class APIError(LLMError):
    """API 调用错误"""
    pass

