"""
OpenAI Provider 实现

支持 OpenAI Chat Completions API，包括多模态和工具调用。

API 文档: https://platform.openai.com/docs/api-reference/chat
"""

import json
import logging
import random
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)

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


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API Provider"""
    
    # thinking_level 到 reasoning effort 的映射
    REASONING_EFFORT_MAP = {
        "minimal": "low",
        "low": "low",
        "medium": "medium",
        "high": "high",
    }
    
    def chat(self, request: ChatRequest) -> ChatResponse:
        """执行 OpenAI Chat Completions API 调用，支持多端点负载均衡。"""
        endpoints = [
            {"api_key": self.config.api_key, "base_url": self.config.get_base_url(), "model": self.config.model},
        ]
        for alt in self.config.alt_endpoints:
            endpoints.append({"api_key": alt["api_key"], "base_url": alt["base_url"].rstrip("/"), "model": alt["model"]})

        if len(endpoints) > 1:
            random.shuffle(endpoints)

        payload_base = self._build_payload(request)

        last_error: Optional[Exception] = None
        for ep in endpoints:
            ep_payload = {**payload_base, "model": ep["model"]}
            url = f"{ep['base_url']}/chat/completions"
            headers = {
                "Authorization": f"Bearer {ep['api_key']}",
                "Content-Type": "application/json",
                **self.config.extra_headers,
            }

            rate_limited = False
            with httpx.Client(timeout=self.config.timeout) as client:
                for attempt in range(self.config.max_retries + 1):
                    try:
                        response = client.post(url, headers=headers, json=ep_payload)
                        return self._parse_response(response)
                    except httpx.TimeoutException:
                        last_error = APIError("Request timeout", status_code=408)
                    except httpx.HTTPStatusError as e:
                        last_error = self._handle_error(e.response)
                    except RateLimitError as e:
                        last_error = e
                        rate_limited = True
                        break
                    except APIError as e:
                        last_error = e
                    if attempt < self.config.max_retries:
                        logger.warning("Attempt %d failed on %s, retrying: %s", attempt + 1, ep["base_url"], last_error)

            if rate_limited:
                logger.warning("Rate limited on %s, trying next endpoint", ep["base_url"])
                continue
            break

        raise last_error  # type: ignore[misc]
    
    def _build_payload(self, request: ChatRequest) -> Dict[str, Any]:
        """构建 OpenAI API 请求体"""
        token_key = "max_completion_tokens" if self.config.provider == "openai" else "max_tokens"
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": self._convert_messages(request.messages),
            token_key: request.max_tokens,
            "temperature": request.temperature,
        }
        
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        
        if request.stop:
            payload["stop"] = request.stop
        
        # 添加工具定义
        if request.tools:
            payload["tools"] = self._convert_tools(request.tools)
        
        # 添加 tool_choice
        if request.tool_choice:
            payload["tool_choice"] = self._convert_tool_choice(request.tool_choice)
        
        # 思考/推理配置
        if request.thinking_level == "disabled":
            if self.config.provider == "kimi":
                payload["thinking"] = {"type": "disabled"}
            else:
                payload["reasoning_effort"] = "none"
        elif request.thinking_level:
            if self.config.provider == "kimi":
                payload["thinking"] = {"type": "enabled"}
            else:
                effort = self.REASONING_EFFORT_MAP.get(request.thinking_level, "medium")
                payload["reasoning_effort"] = effort
        
        return payload
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """将统一消息格式转换为 OpenAI 格式"""
        result = []
        
        for msg in messages:
            converted = {"role": msg.role}
            
            if msg.role == "tool":
                converted["tool_call_id"] = msg.tool_call_id
                if isinstance(msg.content, str):
                    converted["content"] = msg.content
                else:
                    converted["content"] = self._content_to_text(msg.content)
            elif isinstance(msg.content, str):
                converted["content"] = msg.content
            else:
                converted["content"] = self._convert_multimodal_content(msg.content)
            
            if msg.role == "assistant":
                if msg.tool_calls:
                    converted["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                if msg.thinking is not None:
                    converted["reasoning_content"] = msg.thinking
            
            result.append(converted)
        
        return result
    
    def _convert_multimodal_content(
        self, content: List[Union[TextContent, ImageContent, VideoContent]]
    ) -> List[Dict[str, Any]]:
        """转换多模态内容为 OpenAI / Kimi 兼容格式"""
        result = []
        
        for item in content:
            if isinstance(item, TextContent):
                result.append({
                    "type": "text",
                    "text": item.text,
                })
            elif isinstance(item, ImageContent):
                data_url = f"data:{item.media_type};base64,{item.data}"
                result.append({
                    "type": "image_url",
                    "image_url": {
                        "url": data_url,
                    },
                })
            elif isinstance(item, VideoContent):
                data_url = f"data:{item.media_type};base64,{item.data}"
                result.append({
                    "type": "video_url",
                    "video_url": {
                        "url": data_url,
                    },
                })
        
        return result
    
    def _convert_tools(self, tools: List[Tool]) -> List[Dict[str, Any]]:
        """转换工具定义为 OpenAI 格式"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]
    
    def _convert_tool_choice(self, tool_choice: ToolChoice) -> Union[str, Dict[str, Any]]:
        """转换 tool_choice 为 OpenAI 格式"""
        mode_mapping = {
            "auto": "auto",
            "none": "none",
            "required": "required",
        }
        
        if tool_choice.mode in mode_mapping:
            return mode_mapping[tool_choice.mode]
        elif tool_choice.mode == "specific" and tool_choice.tool_name:
            return {
                "type": "function",
                "function": {"name": tool_choice.tool_name},
            }
        
        return "auto"
    
    def _parse_response(self, response: httpx.Response) -> ChatResponse:
        """解析 OpenAI API 响应"""
        if response.status_code != 200:
            raise self._handle_error(response)
        
        data = response.json()
        if "choices" not in data or not data["choices"]:
            error_msg = data.get("error", {}).get("message", "") if isinstance(data.get("error"), dict) else str(data.get("error", ""))
            detail = error_msg or json.dumps(data, ensure_ascii=False)[:500]
            logger.error("API returned 200 but no choices: %s", detail)
            raise APIError(f"API response missing choices: {detail}", status_code=200)
        choice = data["choices"][0]
        message = choice["message"]
        
        # 解析内容
        content = message.get("content")
        
        # 解析 reasoning (o1 等推理模型的思考过程)
        thinking = None
        if "reasoning_content" in message:
            thinking = message["reasoning_content"]
        
        # 解析工具调用
        tool_calls = None
        if "tool_calls" in message and message["tool_calls"]:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"]),
                )
                for tc in message["tool_calls"]
            ]
        
        # 解析 finish_reason
        finish_reason = choice.get("finish_reason", "stop")
        if finish_reason == "tool_calls":
            finish_reason = "tool_calls"
        
        # 解析 usage
        usage = None
        usage_data = data.get("usage", {})
        if usage_data:
            cached = (
                usage_data.get("prompt_cache_hit_tokens")
                or usage_data.get("cached_tokens")
                or 0
            )
            usage = Usage(
                prompt_tokens=usage_data["prompt_tokens"],
                completion_tokens=usage_data["completion_tokens"],
                total_tokens=usage_data.get("total_tokens", 0),
                cached_tokens=cached,
            )

        self._log_usage(response, usage_data)
        
        return ChatResponse(
            content=content,
            thinking=thinking,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            raw_response=data,
        )

    def _log_usage(self, response: httpx.Response, usage_data: dict) -> None:
        """记录 token 用量与 KV cache 命中情况。"""
        parts: list[str] = []

        if usage_data:
            prompt = usage_data.get("prompt_tokens", 0)
            completion = usage_data.get("completion_tokens", 0)
            total = usage_data.get("total_tokens", prompt + completion)
            parts.append(f"tokens: prompt={prompt} completion={completion} total={total}")

            cache_hit = usage_data.get("prompt_cache_hit_tokens") or usage_data.get("cached_tokens")
            cache_miss = usage_data.get("prompt_cache_miss_tokens")
            if cache_hit is not None:
                cache_parts = [f"cache_hit={cache_hit}"]
                if cache_miss is not None:
                    cache_parts.append(f"cache_miss={cache_miss}")
                parts.append(f"prompt_cache: {' '.join(cache_parts)}")

        header_saved = response.headers.get("msh-context-cache-token-saved")
        if header_saved:
            parts.append(f"kv_cache_saved={header_saved}")

        if parts:
            logger.info("LLM usage: %s", "  |  ".join(parts))
    
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

