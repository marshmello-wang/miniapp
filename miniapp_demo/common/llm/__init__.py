"""
LLM 统一接口封装

提供对 OpenAI、Claude、Gemini 等大型语言模型的统一调用接口。

Example:
    基本使用:
    
        >>> from common.llm import LLMClient, LLMConfig, Message
        >>> 
        >>> config = LLMConfig(provider="openai", api_key="sk-xxx", model="gpt-4o")
        >>> client = LLMClient(config)
        >>> 
        >>> response = client.chat(messages=[
        ...     Message(role="system", content="你是一个专业助手"),
        ...     Message(role="user", content="你好"),
        ... ])
        >>> print(response.content)
    
    多模态 (图文):
    
        >>> from common.llm import ImageContent, TextContent
        >>> 
        >>> response = client.chat(messages=[
        ...     Message(role="user", content=[
        ...         TextContent(text="描述这张图片"),
        ...         ImageContent(data="base64...", media_type="image/jpeg"),
        ...     ])
        ... ])
    
    多模态 (视频 - 需要 Kimi 等支持视频理解的 provider):
    
        >>> from common.llm import VideoContent, TextContent
        >>> 
        >>> config = LLMConfig(provider="kimi", api_key="sk-xxx", model="kimi-k2.5")
        >>> client = LLMClient(config)
        >>> response = client.chat(messages=[
        ...     Message(role="user", content=[
        ...         TextContent(text="描述这个视频的内容"),
        ...         VideoContent(data="base64...", media_type="video/mp4"),
        ...     ])
        ... ])
    
    工具调用:
    
        >>> from common.llm import Tool, ToolChoice
        >>> 
        >>> tools = [
        ...     Tool(
        ...         name="get_weather",
        ...         description="获取指定城市的天气",
        ...         parameters={
        ...             "type": "object",
        ...             "properties": {
        ...                 "city": {"type": "string", "description": "城市名称"}
        ...             },
        ...             "required": ["city"]
        ...         }
        ...     )
        ... ]
        >>> 
        >>> response = client.chat(
        ...     messages=[Message(role="user", content="北京天气如何？")],
        ...     tools=tools,
        ...     tool_choice=ToolChoice(mode="auto"),
        ... )
        >>> 
        >>> if response.tool_calls:
        ...     for tc in response.tool_calls:
        ...         print(f"调用工具: {tc.name}, 参数: {tc.arguments}")
    
    快捷创建客户端:
    
        >>> from common.llm import create_client
        >>> 
        >>> client = create_client("claude", "sk-ant-xxx", "claude-3-5-sonnet-20241022")
"""

# 核心类
from .client import LLMClient, create_client
from .config import LLMConfig

# 类型定义
from .types import (
    # 内容类型
    TextContent,
    ImageContent,
    VideoContent,
    ContentType,
    # 消息
    Message,
    # 工具
    Tool,
    ToolChoice,
    ToolCall,
    # 思考
    ThinkingLevel,
    # 请求响应
    ChatRequest,
    ChatResponse,
    Usage,
    # 异常
    LLMError,
    AuthenticationError,
    RateLimitError,
    InvalidRequestError,
    APIError,
)

# 配置常量
from .config import (
    OPENAI_MODELS,
    CLAUDE_MODELS,
    GEMINI_MODELS,
    KIMI_MODELS,
)

# Providers (高级用法)
from .providers import (
    BaseLLMProvider,
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
)

__all__ = [
    # 核心类
    "LLMClient",
    "create_client",
    "LLMConfig",
    # 内容类型
    "TextContent",
    "ImageContent",
    "VideoContent",
    "ContentType",
    # 消息
    "Message",
    # 工具
    "Tool",
    "ToolChoice",
    "ToolCall",
    # 思考
    "ThinkingLevel",
    # 请求响应
    "ChatRequest",
    "ChatResponse",
    "Usage",
    # 异常
    "LLMError",
    "AuthenticationError",
    "RateLimitError",
    "InvalidRequestError",
    "APIError",
    # 配置常量
    "OPENAI_MODELS",
    "CLAUDE_MODELS",
    "GEMINI_MODELS",
    "KIMI_MODELS",
    # Providers
    "BaseLLMProvider",
    "OpenAIProvider",
    "ClaudeProvider",
    "GeminiProvider",
]

__version__ = "0.1.0"

