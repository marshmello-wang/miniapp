"""
Gemini (Google) Provider 实现

支持 Google Gemini API，包括多模态和函数调用。

API 文档: https://ai.google.dev/api/generate-content
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


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider"""
    
    def chat(self, request: ChatRequest) -> ChatResponse:
        """执行 Gemini generateContent API 调用"""
        base_url = self.config.get_base_url()
        model = self.config.model
        url = f"{base_url}/v1beta/models/{model}:generateContent"
        
        # Gemini 使用 query parameter 传递 API key
        params = {"key": self.config.api_key}
        
        headers = {
            "Content-Type": "application/json",
            **self.config.extra_headers,
        }
        
        payload = self._build_payload(request)
        
        with httpx.Client(timeout=self.config.timeout) as client:
            for attempt in range(self.config.max_retries + 1):
                try:
                    response = client.post(url, headers=headers, params=params, json=payload)
                    return self._parse_response(response)
                except httpx.TimeoutException:
                    if attempt == self.config.max_retries:
                        raise APIError("Request timeout", status_code=408)
                except httpx.HTTPStatusError as e:
                    if attempt == self.config.max_retries:
                        raise self._handle_error(e.response)
    
    def _build_payload(self, request: ChatRequest) -> Dict[str, Any]:
        """构建 Gemini API 请求体"""
        # Gemini 需要单独处理 system prompt
        system_prompt, filtered_messages = self._extract_system_prompt(request.messages)
        
        payload: Dict[str, Any] = {
            "contents": self._convert_messages(filtered_messages),
        }
        
        # 添加 system instruction
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }
        
        # 生成配置
        generation_config: Dict[str, Any] = {
            "maxOutputTokens": request.max_tokens,
            "temperature": request.temperature,
        }
        
        if request.top_p is not None:
            generation_config["topP"] = request.top_p
        
        if request.stop:
            generation_config["stopSequences"] = request.stop

        # 添加 thinking 配置 (Gemini 3.0+)                
        if request.thinking_level:
            generation_config["thinkingConfig"] = {
                "thinkingLevel": request.thinking_level.upper(),  # "MINIMAL", "LOW", "MEDIUM", "HIGH"
                "includeThoughts": True
            }
        
        payload["generationConfig"] = generation_config
        
        # 添加工具定义
        if request.tools:
            payload["tools"] = self._convert_tools(request.tools)
        
        # 添加 tool_config
        if request.tool_choice:
            payload["toolConfig"] = self._convert_tool_choice(request.tool_choice, request.tools)
        
        return payload
    
    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """将统一消息格式转换为 Gemini 格式"""
        result = []
        
        for msg in messages:
            role = "model" if msg.role == "assistant" else "user"
            
            if msg.role == "tool":
                if isinstance(msg.content, str):
                    response_obj = {"result": msg.content}
                else:
                    response_obj = {"parts": self._convert_multimodal_content(msg.content)}
                
                result.append({
                    "role": "function",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": msg.name or "",
                                "response": response_obj,
                            }
                        }
                    ],
                })
            elif msg.role == "assistant" and msg.tool_calls:
                parts: List[Dict[str, Any]] = []
                if isinstance(msg.content, str) and msg.content:
                    parts.append({"text": msg.content})
                elif isinstance(msg.content, list):
                    parts.extend(self._convert_multimodal_content(msg.content))
                for tc in msg.tool_calls:
                    parts.append({
                        "functionCall": {
                            "name": tc.name,
                            "args": tc.arguments,
                        }
                    })
                result.append({"role": "model", "parts": parts})
            elif isinstance(msg.content, str):
                result.append({
                    "role": role,
                    "parts": [{"text": msg.content}],
                })
            else:
                result.append({
                    "role": role,
                    "parts": self._convert_multimodal_content(msg.content),
                })
        
        return result
    
    def _convert_multimodal_content(
        self, content: List[Union[TextContent, ImageContent, VideoContent]]
    ) -> List[Dict[str, Any]]:
        """转换多模态内容为 Gemini 格式"""
        result = []
        
        for item in content:
            if isinstance(item, TextContent):
                result.append({"text": item.text})
            elif isinstance(item, ImageContent):
                result.append({
                    "inlineData": {
                        "mimeType": item.media_type,
                        "data": item.data,
                    }
                })
            elif isinstance(item, VideoContent):
                result.append({
                    "inlineData": {
                        "mimeType": item.media_type,
                        "data": item.data,
                    }
                })
        
        return result
    
    def _convert_tools(self, tools: List[Tool]) -> List[Dict[str, Any]]:
        """转换工具定义为 Gemini 格式"""
        function_declarations = [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in tools
        ]
        
        return [{"functionDeclarations": function_declarations}]
    
    def _convert_tool_choice(
        self, tool_choice: ToolChoice, tools: Optional[List[Tool]]
    ) -> Dict[str, Any]:
        """转换 tool_choice 为 Gemini 格式"""
        mode_mapping = {
            "auto": "AUTO",
            "none": "NONE",
            "required": "ANY",
        }
        
        if tool_choice.mode in mode_mapping:
            return {
                "functionCallingConfig": {
                    "mode": mode_mapping[tool_choice.mode]
                }
            }
        elif tool_choice.mode == "specific" and tool_choice.tool_name:
            return {
                "functionCallingConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": [tool_choice.tool_name],
                }
            }
        
        return {"functionCallingConfig": {"mode": "AUTO"}}
    
    def _parse_response(self, response: httpx.Response) -> ChatResponse:
        """解析 Gemini API 响应"""
        if response.status_code != 200:
            raise self._handle_error(response)
        
        data = response.json()
        
        # 检查是否有候选响应
        if "candidates" not in data or not data["candidates"]:
            return ChatResponse(
                content=None,
                finish_reason="stop",
                raw_response=data,
            )
        
        candidate = data["candidates"][0]
        parts = candidate.get("content", {}).get("parts", [])
        
        # 解析内容、思考过程和工具调用
        content = None
        thinking = None
        tool_calls = None
        
        for part in parts:
            if part.get("thought") is True and "text" in part:
                # Gemini thinking 模型的思考过程 (thought: True 标志)
                thinking = part["text"] if thinking is None else thinking + part["text"]
            elif "text" in part:
                # 最终回答 (没有 thought 标志)
                content = part["text"] if content is None else content + part["text"]
            elif "functionCall" in part:
                if tool_calls is None:
                    tool_calls = []
                fc = part["functionCall"]
                # 确保 args 是字典类型（Gemini 可能返回空列表或其他类型）
                args = fc.get("args", {})
                if not isinstance(args, dict):
                    args = {}
                tool_calls.append(
                    ToolCall(
                        id="",  # Gemini 没有单独的 id，ToolCall 会自动生成 UUID
                        name=fc["name"],
                        arguments=args,
                    )
                )
        
        # 解析 finishReason
        finish_reason_raw = candidate.get("finishReason", "STOP")
        finish_reason = "stop"
        if finish_reason_raw == "STOP":
            finish_reason = "stop" if not tool_calls else "tool_calls"
        elif finish_reason_raw == "MAX_TOKENS":
            finish_reason = "length"
        elif finish_reason_raw == "SAFETY":
            finish_reason = "content_filter"
        
        # 解析 usage
        usage = None
        if "usageMetadata" in data:
            cached = data["usageMetadata"].get("cachedContentTokenCount", 0)
            usage = Usage(
                prompt_tokens=data["usageMetadata"].get("promptTokenCount", 0),
                completion_tokens=data["usageMetadata"].get("candidatesTokenCount", 0),
                total_tokens=data["usageMetadata"].get("totalTokenCount", 0),
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
        
        if status_code == 401 or status_code == 403:
            return AuthenticationError(error_message, status_code)
        elif status_code == 429:
            return RateLimitError(error_message, status_code)
        elif status_code == 400:
            return InvalidRequestError(error_message, status_code)
        else:
            return APIError(error_message, status_code)

