"""
协议接口定义 - 定义 Context Strategy 的核心协议和数据结构
"""
from dataclasses import dataclass
from typing import Protocol, Dict, List, Any, Optional, Literal
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.agent_framework.user_interface.inputs import TaskInput
from common.agent_framework.user_interface.events import Event
from common.agent_framework.tool_adapter.protocol import ToolSchema
from common.llm import ChatRequest


# ============================================================================
# 环境状态定义
# ============================================================================

@dataclass
class EnvironmentState:
    """
    环境状态 - 在上下文中唯一，持续更新
    
    用于表示容器状态、产物状态等需要在上下文中保持唯一且持续更新的信息。
    
    Attributes:
        key: 唯一标识（如 "container_status", "artifact_state"）
        content: 状态内容（字符串形式）
        position: 在上下文中的拼接位置
            - "system": 拼接到 system prompt 末尾
            - "user_prefix": 作为最新 user message 的前缀
            - "assistant_suffix": 作为最新 assistant message 的后缀
        priority: 同位置下的排序优先级（数值越小越靠前）
    
    Example:
        >>> container_state = EnvironmentState(
        ...     key="container_status",
        ...     content="Container ID: abc123\\nStatus: Running\\nPorts: 8080:80",
        ...     position="system",
        ...     priority=10
        ... )
    """
    key: str
    content: str
    position: Literal["system", "user_prefix", "assistant_suffix"]
    priority: int = 0
    
    def __post_init__(self):
        """验证参数合法性"""
        valid_positions = {"system", "user_prefix", "assistant_suffix"}
        if self.position not in valid_positions:
            raise ValueError(f"position must be one of {valid_positions}, got '{self.position}'")


# ============================================================================
# Context Strategy 协议
# ============================================================================

class ContextStrategy(Protocol):
    """
    上下文策略协议 - 不同 agent 实现自己的策略
    
    这是 agent 的核心业务逻辑接口，负责将各种输入转换为模型可用的上下文。
    
    设计原则：
    - 纯函数式接口，无状态
    - 不同 agent 根据自身需求实现不同策略
    - 支持环境状态的特殊处理
    
    Example:
        >>> class MyAgentStrategy:
        ...     def build_context(self, task_input, events, environment_states, 
        ...                       system_prompt, tools=None):
        ...         # 自定义上下文构建逻辑
        ...         ...
        ...         return model_context
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
        
        Args:
            task_input: 用户输入的任务（包含 session_id, task_id, messages 等）
            events: Agent 执行轨迹（tool_call, reasoning 等事件列表）
            environment_states: 环境状态字典（key -> EnvironmentState）
            system_prompt: 当前的 system prompt（可能已被修改）
            tools: 可用的工具列表（可选）
        
        Returns:
            ChatRequest: 构建好的模型调用请求（使用 common.llm.ChatRequest）
        
        Note:
            - events 按时间顺序排列
            - environment_states 中同 key 的状态已被去重（保留最新）
            - system_prompt 可能已被 ContextBuilder 动态修改
        """
        ...


# ============================================================================
# 类型别名
# ============================================================================

# System Prompt 修改函数类型
SystemPromptModifier = type(lambda prompt: prompt)  # Callable[[str], str]

