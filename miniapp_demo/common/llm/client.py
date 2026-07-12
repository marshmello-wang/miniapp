"""
LLM Client 入口

提供统一的 LLM 调用接口，根据配置自动选择对应的 Provider。
"""

import logging
from typing import List, Optional

from .config import LLMConfig
from .providers import BaseLLMProvider, ClaudeProvider, GeminiProvider, OpenAIProvider
from .types import (
    ChatRequest,
    ChatResponse,
    ImageContent,
    Message,
    TextContent,
    ThinkingLevel,
    Tool,
    ToolChoice,
    VideoContent,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """
    统一的 LLM 客户端
    
    根据配置自动选择对应的 Provider (OpenAI, Claude, Gemini)。
    
    Example:
        >>> config = LLMConfig(provider="openai", api_key="sk-xxx", model="gpt-4o")
        >>> client = LLMClient(config)
        >>> response = client.chat(messages=[Message(role="user", content="你好")])
        >>> print(response.content)
    """
    
    def __init__(self, config: LLMConfig):
        """
        初始化 LLM 客户端
        
        Args:
            config: LLM 配置对象
        """
        self.config = config
        self._provider = self._create_provider()
    
    def _create_provider(self) -> BaseLLMProvider:
        """根据配置创建对应的 Provider。

        当 claude / gemini 设置了自定义 base_url（即通过代理访问）时，
        使用 OpenAIProvider，因为代理服务通常提供 OpenAI 兼容接口。
        """
        if self.config.base_url and self.config.provider in ("claude", "gemini"):
            return OpenAIProvider(self.config)

        provider_map = {
            "openai": OpenAIProvider,
            "claude": ClaudeProvider,
            "gemini": GeminiProvider,
            "kimi": OpenAIProvider,
        }
        
        provider_class = provider_map.get(self.config.provider)
        if provider_class is None:
            raise ValueError(f"Unsupported provider: {self.config.provider}")
        
        return provider_class(self.config)
    
    @property
    def provider(self) -> BaseLLMProvider:
        """获取当前使用的 Provider"""
        return self._provider
    
    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        tool_choice: Optional[ToolChoice] = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        top_p: Optional[float] = None,
        stop: Optional[List[str]] = None,
        thinking_level: Optional[ThinkingLevel] = None,
    ) -> ChatResponse:
        request = ChatRequest(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
            thinking_level=thinking_level,
        )

        self._log_context(request)
        response = self._provider.chat(request)
        self._log_response(response)
        return response

    def chat_with_request(self, request: ChatRequest) -> ChatResponse:
        self._log_context(request)
        response = self._provider.chat(request)
        self._log_response(response)
        return response

    # ------------------------------------------------------------------
    # Context logging
    # ------------------------------------------------------------------

    def _log_context(self, request: ChatRequest) -> None:
        """打印本次 LLM 请求的完整消息上下文（image/video 用摘要替代）。"""
        if not logger.isEnabledFor(logging.INFO):
            return

        lines: List[str] = [
            "",
            "=" * 72,
            f"LLM REQUEST  model={self.config.model}  "
            f"max_tokens={request.max_tokens}  temp={request.temperature}",
            "=" * 72,
        ]

        for idx, msg in enumerate(request.messages):
            lines.append(f"--- [{idx}] role={msg.role} ---")
            lines.extend(self._summarize_content(msg.content))

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    lines.append(f"  [tool_call] {tc.name}({tc.arguments})")

        if request.tools:
            names = [t.name for t in request.tools]
            lines.append(f"--- tools: {names} ---")

        lines.append("=" * 72)
        logger.info("\n".join(lines))

    def _log_response(self, response: "ChatResponse") -> None:
        """记录 LLM 响应内容（截断过长文本）。"""
        if not logger.isEnabledFor(logging.INFO):
            return

        max_len = 5000
        lines: List[str] = [
            "",
            "-" * 72,
            f"LLM RESPONSE  model={self.config.model}  "
            f"finish_reason={response.finish_reason}",
            "-" * 72,
        ]

        if response.thinking:
            t = response.thinking if len(response.thinking) <= max_len else response.thinking[:max_len] + "…"
            lines.append(f"  [thinking] {t}")

        if response.content:
            c = response.content if len(response.content) <= max_len else response.content[:max_len] + "…"
            lines.append(f"  [content] {c}")

        if response.tool_calls:
            for tc in response.tool_calls:
                lines.append(f"  [tool_call] {tc.name}({tc.arguments})")

        if response.usage:
            u = response.usage
            lines.append(
                f"  [usage] prompt={u.prompt_tokens} completion={u.completion_tokens} total={u.total_tokens}"
            )

        lines.append("-" * 72)
        logger.info("\n".join(lines))

    @staticmethod
    def _summarize_content(content, max_text_len: int = 5000) -> List[str]:
        """将消息 content 转为可读的摘要行列表。"""
        if isinstance(content, str):
            text = content if len(content) <= max_text_len else content[:max_text_len] + "…"
            return [f"  {text}"]

        parts: List[str] = []
        if not isinstance(content, list):
            return [f"  {content!r}"]

        for item in content:
            if isinstance(item, TextContent):
                t = item.text if len(item.text) <= max_text_len else item.text[:max_text_len] + "…"
                parts.append(f"  [text] {t}")
            elif isinstance(item, ImageContent):
                kb = len(item.data) * 3 // 4 // 1024
                parts.append(f"  [image] {item.media_type}  ~{kb} KB")
            elif isinstance(item, VideoContent):
                kb = len(item.data) * 3 // 4 // 1024
                parts.append(f"  [video] {item.media_type}  ~{kb} KB")
            else:
                parts.append(f"  [unknown] {type(item).__name__}")
        return parts


def create_client(
    provider: str,
    api_key: str,
    model: str,
    base_url: Optional[str] = None,
    timeout: int = 60,
    max_retries: int = 2,
) -> LLMClient:
    """
    创建 LLM 客户端的快捷函数
    
    Args:
        provider: 服务提供商 ("openai" | "claude" | "gemini")
        api_key: API 密钥
        model: 模型名称
        base_url: 自定义 API 端点 (可选)
        timeout: 请求超时时间 (秒)
        max_retries: 最大重试次数
        
    Returns:
        LLMClient: 配置好的客户端实例
        
    Example:
        >>> client = create_client("openai", "sk-xxx", "gpt-4o")
        >>> response = client.chat(messages=[Message(role="user", content="Hello")])
    """
    config = LLMConfig(
        provider=provider,  # type: ignore
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
    )
    return LLMClient(config)

