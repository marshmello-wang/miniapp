"""
默认上下文策略 - 作为示例实现
"""
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.agent_framework.user_interface.inputs import TaskInput, Message, MessageContent
from common.agent_framework.user_interface.events import Event
from common.agent_framework.user_interface.content_blocks import (
    ContentBlock, TextBlock, ThinkingBlock, ToolCallBlock, ToolResultBlock
)
from common.agent_framework.tool_adapter.protocol import ToolSchema
from common.llm import (
    ChatRequest, Message as LLMMessage, Tool as LLMTool,
    TextContent, ImageContent as LLMImageContent, VideoContent as LLMVideoContent,
    ToolCall
)

from .protocol import ContextStrategy, EnvironmentState


@dataclass
class DefaultContextStrategy:
    """
    默认上下文策略 - 作为 example 实现
    
    功能：
    - 将 TaskInput.messages 转换为 ChatMessage
    - 按时间顺序处理 events，转换为对话消息
    - 将 environment_states 按 position 拼接到对应位置
    
    这是一个基础实现，展示了如何实现 ContextStrategy 协议。
    实际 agent 应根据自身需求实现自己的策略。
    
    Example:
        >>> strategy = DefaultContextStrategy()
        >>> context = strategy.build_context(
        ...     task_input=task_input,
        ...     events=events,
        ...     environment_states=env_states,
        ...     system_prompt="You are helpful.",
        ...     tools=tools
        ... )
    """
    
    def build_context(
        self,
        task_input: TaskInput,
        events: List[Event],
        environment_states: Dict[str, EnvironmentState],
        system_prompt: str,
        tools: Optional[List[ToolSchema]] = None
    ) -> ChatRequest:
        """
        构建模型调用上下文
        
        处理流程：
        1. 处理 system prompt + system 位置的环境状态
        2. 转换 task_input.messages 为初始消息
        3. 按时间顺序处理 events，转换为对话消息
        4. 处理 user_prefix 和 assistant_suffix 位置的环境状态
        
        Args:
            task_input: 用户输入的任务
            events: Agent 执行轨迹
            environment_states: 环境状态字典
            system_prompt: 当前的 system prompt
            tools: 可用的工具列表
        
        Returns:
            ChatRequest: 构建好的模型调用请求
        """
        # 1. 构建 system prompt（包含 system 位置的环境状态）
        final_system_prompt = self._build_system_prompt(system_prompt, environment_states)
        
        # 2. 转换初始消息
        messages: List[LLMMessage] = []
        
        # 添加 system prompt 作为第一条消息
        if final_system_prompt:
            messages.append(LLMMessage(role="system", content=final_system_prompt))
        
        # 转换用户输入的消息
        for msg in task_input.messages:
            llm_msg = self._convert_message(msg)
            messages.append(llm_msg)
        
        # 3. 处理 events，转换为对话消息
        event_messages = self._process_events(events)
        messages.extend(event_messages)
        
        # 4. 处理 user_prefix 和 assistant_suffix 位置的环境状态
        messages = self._apply_environment_states(messages, environment_states)
        
        # 5. 转换工具 schema 为 LLMTool
        llm_tools = None
        if tools:
            llm_tools = [
                LLMTool(
                    name=t.name,
                    description=t.description,
                    parameters=t.schema
                )
                for t in tools
            ]
        
        # 6. 构建 ChatRequest
        return ChatRequest(
            messages=messages,
            tools=llm_tools
        )
    
    def _build_system_prompt(
        self,
        base_prompt: str,
        environment_states: Dict[str, EnvironmentState]
    ) -> str:
        """
        构建 system prompt，包含 system 位置的环境状态
        
        Args:
            base_prompt: 基础 system prompt
            environment_states: 环境状态字典
        
        Returns:
            拼接后的 system prompt
        """
        # 筛选 system 位置的环境状态，按 priority 排序
        system_states = [
            s for s in environment_states.values()
            if s.position == "system"
        ]
        system_states.sort(key=lambda s: s.priority)
        
        if not system_states:
            return base_prompt
        
        # 拼接环境状态到 system prompt 末尾
        parts = [base_prompt]
        for state in system_states:
            parts.append(f"\n\n## {state.key}\n{state.content}")
        
        return "".join(parts)
    
    def _convert_message(self, msg: Message) -> LLMMessage:
        """
        将 user_interface 的 Message 转换为 common.llm 的 Message
        
        Args:
            msg: 原始消息
        
        Returns:
            转换后的 LLMMessage
        """
        # 如果只有一个文本内容，直接使用字符串
        if len(msg.content) == 1 and msg.content[0].type == "text" and msg.content[0].text:
            return LLMMessage(role=msg.role, content=msg.content[0].text)
        
        # 多内容情况，构建内容列表
        content_parts: List[Union[TextContent, LLMImageContent, LLMVideoContent]] = []
        
        for item in msg.content:
            if item.type == "text" and item.text:
                content_parts.append(TextContent(text=item.text))
            elif item.type == "image" and item.image:
                content_parts.append(LLMImageContent(
                    data=item.image.data,
                    media_type=item.image.mime_type or "image/jpeg"
                ))
            elif item.type == "video" and item.video:
                content_parts.append(LLMVideoContent(
                    data=item.video.data,
                    media_type=item.video.mime_type or "video/mp4"
                ))
        
        return LLMMessage(role=msg.role, content=content_parts)
    
    def _process_events(self, events: List[Event]) -> List[LLMMessage]:
        """
        处理事件列表，转换为对话消息
        
        支持的事件类型：
        - reasoning_complete / reasoning: 转换为 assistant 消息
        - tool_call: 转换为 assistant 消息（包含工具调用）
        - tool_result: 转换为 tool 消息
        
        Args:
            events: 事件列表
        
        Returns:
            转换后的消息列表
        """
        messages: List[LLMMessage] = []
        
        pending_text: Optional[str] = None
        pending_thinking: Optional[str] = None
        pending_tool_calls: List[ToolCall] = []
        
        for event in events:
            if event.event_type in ("reasoning_complete", "reasoning"):
                text = self._extract_text_from_content(event.content)
                if text:
                    pending_text = text
                
                for block in event.content:
                    if isinstance(block, ThinkingBlock) and block.thinking:
                        pending_thinking = block.thinking
                    elif isinstance(block, ToolCallBlock):
                        pending_tool_calls.append(ToolCall(
                            id=block.call_id or "",
                            name=block.tool_name,
                            arguments=block.tool_input
                        ))
            
            elif event.event_type == "tool_result":
                if pending_text or pending_tool_calls:
                    messages.append(self._create_assistant_message(
                        pending_text, pending_tool_calls, pending_thinking
                    ))
                    pending_text = None
                    pending_thinking = None
                    pending_tool_calls = []
                
                for block in event.content:
                    if isinstance(block, ToolResultBlock):
                        result_str = str(block.result) if block.result is not None else ""
                        if block.is_error and block.error_message:
                            result_str = f"Error: {block.error_message}"
                        messages.append(LLMMessage(
                            role="tool",
                            content=result_str,
                            tool_call_id=block.call_id or "",
                            name=block.tool_name
                        ))
        
        if pending_text or pending_tool_calls:
            messages.append(self._create_assistant_message(
                pending_text, pending_tool_calls, pending_thinking
            ))
        
        return messages
    
    def _extract_text_from_content(self, content: List[ContentBlock]) -> Optional[str]:
        """从内容块列表中提取文本"""
        texts = []
        for block in content:
            if isinstance(block, TextBlock):
                texts.append(block.text)
        return "\n".join(texts) if texts else None
    
    def _create_assistant_message(
        self,
        text: Optional[str],
        tool_calls: List[ToolCall],
        thinking: Optional[str] = None,
    ) -> LLMMessage:
        """创建 assistant 消息"""
        return LLMMessage(
            role="assistant",
            content=text or "",
            tool_calls=tool_calls if tool_calls else None,
            thinking=thinking,
        )
    
    def _apply_environment_states(
        self,
        messages: List[LLMMessage],
        environment_states: Dict[str, EnvironmentState]
    ) -> List[LLMMessage]:
        """
        应用 user_prefix 和 assistant_suffix 位置的环境状态
        
        Args:
            messages: 消息列表
            environment_states: 环境状态字典
        
        Returns:
            处理后的消息列表
        """
        if not messages or not environment_states:
            return messages
        
        # 筛选并排序 user_prefix 状态
        user_prefix_states = sorted(
            [s for s in environment_states.values() if s.position == "user_prefix"],
            key=lambda s: s.priority
        )
        
        # 筛选并排序 assistant_suffix 状态
        assistant_suffix_states = sorted(
            [s for s in environment_states.values() if s.position == "assistant_suffix"],
            key=lambda s: s.priority
        )
        
        # 找到最后一条 user 消息，添加 prefix
        if user_prefix_states:
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].role == "user":
                    prefix_text = "\n".join([
                        f"[{s.key}]\n{s.content}" for s in user_prefix_states
                    ])
                    # 在消息内容前添加环境状态
                    current_content = messages[i].content
                    if isinstance(current_content, str):
                        new_content = prefix_text + "\n\n" + current_content
                    else:
                        new_content = [TextContent(text=prefix_text + "\n\n")] + current_content
                    messages[i] = LLMMessage(role="user", content=new_content)
                    break
        
        # 找到最后一条 assistant 消息，添加 suffix
        if assistant_suffix_states:
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].role == "assistant":
                    suffix_text = "\n".join([
                        f"[{s.key}]\n{s.content}" for s in assistant_suffix_states
                    ])
                    # 在消息内容后添加环境状态
                    current_content = messages[i].content
                    if isinstance(current_content, str):
                        new_content = current_content + "\n\n" + suffix_text
                    else:
                        new_content = current_content + [TextContent(text="\n\n" + suffix_text)]
                    messages[i] = LLMMessage(role="assistant", content=new_content)
                    break
        
        return messages

