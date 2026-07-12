"""
LLM Provider 抽象基类

定义所有 LLM Provider 必须实现的接口。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from ..config import LLMConfig
from ..types import (
    ChatRequest,
    ChatResponse,
    ImageContent,
    Message,
    TextContent,
    Tool,
    ToolCall,
    ToolChoice,
    Usage,
    VideoContent,
)


class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
    
    @abstractmethod
    def chat(self, request: ChatRequest) -> ChatResponse:
        """
        执行聊天请求
        
        Args:
            request: 聊天请求对象
            
        Returns:
            ChatResponse: 聊天响应对象
        """
        pass
    
    def _extract_system_prompt(self, messages: List[Message]) -> tuple[Optional[str], List[Message]]:
        """
        从消息列表中提取 system prompt
        
        Args:
            messages: 消息列表
            
        Returns:
            tuple: (system_prompt, filtered_messages)
        """
        system_prompt = None
        filtered_messages = []
        
        for msg in messages:
            if msg.role == "system":
                # 只取第一个 system 消息，后续的合并到 content
                if system_prompt is None:
                    if isinstance(msg.content, str):
                        system_prompt = msg.content
                    elif isinstance(msg.content, list):
                        # 提取文本内容
                        texts = [
                            item.text if isinstance(item, TextContent) else ""
                            for item in msg.content
                        ]
                        system_prompt = "\n".join(filter(None, texts))
                else:
                    # 多个 system 消息，合并
                    if isinstance(msg.content, str):
                        system_prompt += "\n" + msg.content
            else:
                filtered_messages.append(msg)
        
        return system_prompt, filtered_messages
    
    def _content_to_text(self, content: Union[str, List[Union[TextContent, ImageContent, VideoContent]]]) -> str:
        """将 content 转换为纯文本（图片/视频被忽略）"""
        if isinstance(content, str):
            return content
        
        texts = []
        for item in content:
            if isinstance(item, TextContent):
                texts.append(item.text)
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)

