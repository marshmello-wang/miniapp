"""
Claude (Anthropic) Provider 实现

支持 Anthropic Messages API，包括多模态和工具调用。

API 文档: https://docs.anthropic.com/en/api/messages
"""

import json
from typing import Any, Dict, List, Optional, Union

import httpx

from ..config import LLMConfig
from ..types import (
    APIError,
    AuthenticationError,
    ChatRequest,
    ChatResponse,
    ImageContent,
    InvalidRequestError,
    Message,
    RateLimitError,
    TextContent,
    Tool,
    ToolCall,
    ToolChoice,
    Usage,
    VideoContent,
)
from .base import BaseLLMProvider


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude API Provider"""
    
    # Claude API 版本
    ANTHROPIC_VERSION = "2023-06-01"
    
    # thinking_level 到 budget_tokens 的映射
    THINKING_BUDGET_MAP = {
        "minimal": 1024,
        "low": 1024,
        "medium": 4096,
        "high": 16384,
    }
    
    def chat(self, request: ChatRequest) -> ChatResponse:
        """执行 Claude Messages API 调用"""
        url = f"{self.config.get_base_url()}/v1/messages"
        
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
            **self.config.extra_headers,
        }
        
        payload = self._build_payload(request)
        
        with httpx.Client(timeout=self.config.timeout) as client:
            for attempt in range(self.config.max_retries + 1):
                try:
                    response = client.post(url, headers=headers, json=payload)
                    return self._parse_response(response)
                except httpx.TimeoutException:
                    if attempt == self.config.max_retries:
                        raise APIError("Request timeout", status_code=408)
                except httpx.HTTPStatusError as e:
                    if attempt == self.config.max_retries:
                        raise self._handle_error(e.response)
    
    def _build_payload(self, request: ChatRequest) -> Dict[str, Any]:
        """构建 Claude API 请求体"""
        # Claude 需要单独处理 system prompt
        system_prompt, filtered_messages = self._extract_system_prompt(request.messages)
        
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": self._convert_messages(filtered_messages),
            "max_tokens": request.max_tokens,
        }

        # 添加 system prompt
        if system_prompt:
            payload["system"] = system_prompt
        
        # 温度参数 (Claude 的范围是 0-1)
        if request.temperature is not None:
            payload["temperature"] = min(request.temperature, 1.0)
        
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        
        if request.stop:
            payload["stop_sequences"] = request.stop
        
        # 添加工具定义
        if request.tools:
            payload["tools"] = self._convert_tools(request.tools)
        
        # 添加 tool_choice
        if request.tool_choice:
            payload["tool_choice"] = self._convert_tool_choice(request.tool_choice)
        
        # 添加 thinking 配置 (Claude extended thinking)
        if request.thinking_level:
            budget_tokens = self.THINKING_BUDGET_MAP.get(request.thinking_level, 10240)
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": budget_tokens,
            }
            payload["max_tokens"] = payload["max_tokens"] + budget_tokens
        
        return payload
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """将统一消息格式转换为 Claude 格式"""
        result = []
        
        for msg in messages:
            if msg.role == "tool":
                tool_result: Dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                }
                if isinstance(msg.content, str):
                    tool_result["content"] = msg.content
                else:
                    tool_result["content"] = self._convert_multimodal_content(msg.content)
                
                result.append({
                    "role": "user",
                    "content": [tool_result],
                })
            elif msg.role == "assistant" and msg.tool_calls:
                content_blocks: List[Dict[str, Any]] = []
                if isinstance(msg.content, str) and msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                elif isinstance(msg.content, list):
                    content_blocks.extend(self._convert_multimodal_content(msg.content))
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                result.append({
                    "role": "assistant",
                    "content": content_blocks,
                })
            elif isinstance(msg.content, str):
                result.append({
                    "role": msg.role,
                    "content": msg.content,
                })
            else:
                result.append({
                    "role": msg.role,
                    "content": self._convert_multimodal_content(msg.content),
                })
        
        return result
    
    def _convert_multimodal_content(
        self, content: List[Union[TextContent, ImageContent, VideoContent]]
    ) -> List[Dict[str, Any]]:
        """转换多模态内容为 Claude 格式"""
        result = []
        
        for item in content:
            if isinstance(item, TextContent):
                result.append({
                    "type": "text",
                    "text": item.text,
                })
            elif isinstance(item, ImageContent):
                result.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": item.media_type,
                        "data": item.data,
                    },
                })
            elif isinstance(item, VideoContent):
                result.append({
                    "type": "video",
                    "source": {
                        "type": "base64",
                        "media_type": item.media_type,
                        "data": item.data,
                    },
                })
        
        return result
    
    def _convert_tools(self, tools: List[Tool]) -> List[Dict[str, Any]]:
        """转换工具定义为 Claude 格式"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]
    
    def _convert_tool_choice(self, tool_choice: ToolChoice) -> Dict[str, Any]:
        """转换 tool_choice 为 Claude 格式"""
        if tool_choice.mode == "auto":
            return {"type": "auto"}
        elif tool_choice.mode == "required":
            return {"type": "any"}
        elif tool_choice.mode == "specific" and tool_choice.tool_name:
            return {"type": "tool", "name": tool_choice.tool_name}
        # Claude 没有 "none" 模式，默认返回 auto
        return {"type": "auto"}
    
    def _parse_response(self, response: httpx.Response) -> ChatResponse:
        """解析 Claude API 响应"""
        if response.status_code != 200:
            raise self._handle_error(response)
        
        data = response.json()
        
        # 解析内容、思考过程和工具调用
        content = None
        thinking = None
        tool_calls = None
        
        for block in data.get("content", []):
            if block["type"] == "thinking":
                # Claude extended thinking 的思考过程
                thinking = block["thinking"] if thinking is None else thinking + block["thinking"]
            elif block["type"] == "text":
                content = block["text"] if content is None else content + block["text"]
            elif block["type"] == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=block["input"],
                    )
                )
        
        # 解析 stop_reason
        stop_reason = data.get("stop_reason", "end_turn")
        finish_reason = "stop"
        if stop_reason == "tool_use":
            finish_reason = "tool_calls"
        elif stop_reason == "max_tokens":
            finish_reason = "length"
        
        # 解析 usage
        usage = None
        if "usage" in data:
            cached = data["usage"].get("cache_read_input_tokens", 0)
            usage = Usage(
                prompt_tokens=data["usage"]["input_tokens"],
                completion_tokens=data["usage"]["output_tokens"],
                cached_tokens=cached,
            )
        
        return ChatResponse(
            content=content,
            thinking=thinking,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            raw_response=data,
        )
    
    def _handle_error(self, response: httpx.Response) -> Exception:
        """处理 API 错误"""
        try:
            error_data = response.json()
            error_message = error_data.get("error", {}).get("message", str(response.text))
        except Exception:
            error_message = response.text
        
        status_code = response.status_code
        
        if status_code == 401:
            return AuthenticationError(error_message, status_code)
        elif status_code == 429:
            return RateLimitError(error_message, status_code)
        elif status_code == 400:
            return InvalidRequestError(error_message, status_code)
        else:
            return APIError(error_message, status_code)

