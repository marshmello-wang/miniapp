"""
上下文构建器 - 有状态的上下文管理
"""
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.agent_framework.user_interface.inputs import TaskInput
from common.agent_framework.user_interface.events import Event
from common.agent_framework.tool_adapter.protocol import ToolSchema
from common.llm import ChatRequest

from .protocol import ContextStrategy, EnvironmentState
from .truncation import TruncationStrategy, NoTruncation
from .memory.helper import ContextMemoryHelper


class ContextBuilder:
    """
    上下文构建器 - 在 task 维度内保持状态
    
    职责：
    - 管理事件累积
    - 管理环境状态更新
    - 管理 system prompt 修改
    - 调用 ContextStrategy 构建最终上下文
    
    生命周期：
    - 一个 ContextBuilder 实例对应一个 task（一次 react loop）
    - reset() 方法可重置状态，开始新 task
    
    Example:
        >>> builder = ContextBuilder(
        ...     strategy=MyStrategy(),
        ...     base_system_prompt="You are a helpful assistant.",
        ...     tools=[tool1, tool2]
        ... )
        >>> builder.reset(task_input)
        >>> 
        >>> # 在 react loop 中
        >>> builder.add_event(reasoning_event)
        >>> builder.update_environment("container", container_state)
        >>> context = builder.build()  # 获取 ModelContext 用于模型调用
        >>> 
        >>> # 工具执行后
        >>> builder.add_event(tool_result_event)
        >>> context = builder.build()  # 获取更新后的上下文
    """
    
    def __init__(
        self,
        strategy: ContextStrategy,
        base_system_prompt: str,
        truncation: Optional[TruncationStrategy] = None,
        memory: Optional[ContextMemoryHelper] = None,
        tools: Optional[List[ToolSchema]] = None
    ):
        """
        初始化上下文构建器
        
        Args:
            strategy: 上下文策略实例（决定如何构建上下文）
            base_system_prompt: 基础 system prompt（由 agent 配置）
            truncation: 截断策略（可选，已废弃，优先使用 memory）
            memory: Memory 截断 Helper（可选，替代 truncation）
            tools: 可用工具列表（可选）
        """
        self._strategy = strategy
        self._base_system_prompt = base_system_prompt
        self._truncation = truncation or NoTruncation()
        self._memory = memory
        self._tools = tools
        
        # 状态
        self._task_input: Optional[TaskInput] = None
        self._events: List[Event] = []
        self._environment_states: Dict[str, EnvironmentState] = {}
        self._system_prompt_modifiers: List[Callable[[str], str]] = []
        self._current_system_prompt: str = base_system_prompt
        
        # Skill binding tools: skill_name -> List[ToolSchema]
        self._skill_tools: Dict[str, List[ToolSchema]] = {}
    
    @property
    def task_input(self) -> Optional[TaskInput]:
        """当前任务输入"""
        return self._task_input
    
    @property
    def events(self) -> List[Event]:
        """当前累积的事件列表（只读副本）"""
        return self._events.copy()
    
    @property
    def environment_states(self) -> Dict[str, EnvironmentState]:
        """当前环境状态字典（只读副本）"""
        return self._environment_states.copy()
    
    @property
    def current_system_prompt(self) -> str:
        """当前的 system prompt（已应用所有修改器）"""
        return self._current_system_prompt
    
    @property
    def tools(self) -> Optional[List[ToolSchema]]:
        """可用工具列表"""
        return self._tools
    
    # ========================================================================
    # 状态管理方法
    # ========================================================================
    
    def reset(self, task_input: TaskInput) -> None:
        """
        重置状态，开始新任务
        
        Args:
            task_input: 新任务的输入
        
        Note:
            - 清空所有累积的事件和环境状态
            - 重置 system prompt 到基础值
            - 保留 strategy、truncation/memory、tools 配置
            - 保留 skill_tools（skill 生命周期跨 task）
        """
        self._task_input = task_input
        self._events = []
        self._environment_states = {}
        self._system_prompt_modifiers = []
        self._current_system_prompt = self._base_system_prompt
    
    def add_event(self, event: Event) -> None:
        """
        添加执行事件
        
        Args:
            event: Agent 执行事件（如 reasoning、tool_call、tool_result 等）
        
        Note:
            事件按添加顺序保存，保持时间顺序
        """
        self._events.append(event)
    
    def add_events(self, events: List[Event]) -> None:
        """
        批量添加执行事件
        
        Args:
            events: 事件列表
        """
        self._events.extend(events)
    
    def update_environment(self, key: str, state: EnvironmentState) -> None:
        """
        更新环境状态
        
        Args:
            key: 环境状态的唯一标识
            state: 新的环境状态
        
        Note:
            - 同 key 的状态会被覆盖
            - state.key 应与参数 key 一致
        """
        if state.key != key:
            raise ValueError(f"state.key ({state.key}) does not match key ({key})")
        self._environment_states[key] = state
    
    def remove_environment(self, key: str) -> bool:
        """
        移除环境状态
        
        Args:
            key: 要移除的环境状态的唯一标识
        
        Returns:
            是否成功移除（key 不存在时返回 False）
        """
        if key in self._environment_states:
            del self._environment_states[key]
            return True
        return False
    
    def modify_system_prompt(self, modifier: Callable[[str], str]) -> None:
        """
        添加 system prompt 修改器
        
        Args:
            modifier: 修改函数，接收当前 prompt，返回修改后的 prompt
        
        Example:
            >>> # 添加技能描述
            >>> builder.modify_system_prompt(
            ...     lambda p: p + "\\n\\n## Available Skills\\n- Web Search\\n- Code Execution"
            ... )
        
        Note:
            - 修改器按添加顺序链式执行
            - 立即应用到 current_system_prompt
        """
        self._system_prompt_modifiers.append(modifier)
        self._current_system_prompt = modifier(self._current_system_prompt)
    
    def reset_system_prompt(self) -> None:
        """
        重置 system prompt 到基础值
        
        清除所有修改器，恢复到 base_system_prompt
        """
        self._system_prompt_modifiers = []
        self._current_system_prompt = self._base_system_prompt
    
    def set_tools(self, tools: List[ToolSchema]) -> None:
        """
        设置可用工具列表
        
        Args:
            tools: 新的工具列表
        """
        self._tools = tools
    
    def add_tool(self, tool: ToolSchema) -> None:
        """
        添加单个工具
        
        Args:
            tool: 要添加的工具
        """
        if self._tools is None:
            self._tools = []
        self._tools.append(tool)
    
    # ========================================================================
    # Skill Tools 管理方法
    # ========================================================================
    
    def add_skill_tools(self, skill_name: str, tools: List[ToolSchema]) -> None:
        """
        添加某 skill 的 binding tools
        
        Args:
            skill_name: skill 名称
            tools: 该 skill 关联的 tool schemas
        """
        self._skill_tools[skill_name] = tools
    
    def remove_skill_tools(self, skill_name: str) -> bool:
        """
        移除某 skill 的 binding tools
        
        Args:
            skill_name: skill 名称
        
        Returns:
            是否成功移除
        """
        if skill_name in self._skill_tools:
            del self._skill_tools[skill_name]
            return True
        return False
    
    def get_all_tools(self) -> Optional[List[ToolSchema]]:
        """
        合并常规 tools 和所有活跃 skill 的 binding tools（按 name 去重）。
        
        Returns:
            合并后的 tool 列表，如果没有任何 tool 则返回 None
        """
        seen_names: Dict[str, ToolSchema] = {}
        
        # 常规 tools 优先
        if self._tools:
            for t in self._tools:
                seen_names[t.name] = t
        
        # 追加 skill tools（同名不覆盖常规 tool）
        for tools_list in self._skill_tools.values():
            for t in tools_list:
                if t.name not in seen_names:
                    seen_names[t.name] = t
        
        if not seen_names:
            return None
        return list(seen_names.values())
    
    # ========================================================================
    # 构建方法
    # ========================================================================
    
    def build(self) -> ChatRequest:
        """
        构建模型调用上下文

        优先使用 memory (ContextMemoryHelper) 进行 L1 截断；
        若未配置 memory 则回退到 legacy truncation 策略。
        
        Returns:
            ChatRequest: 构建好的请求，可直接用于 LLMClient.chat_with_request()
        
        Raises:
            ValueError: 如果未调用 reset() 设置 task_input
        """
        if self._task_input is None:
            raise ValueError("task_input is not set. Call reset() first.")
        
        # 合并 tools
        merged_tools = self.get_all_tools()
        
        # 使用策略构建上下文
        context = self._strategy.build_context(
            task_input=self._task_input,
            events=self._events,
            environment_states=self._environment_states,
            system_prompt=self._current_system_prompt,
            tools=merged_tools
        )
        
        # 应用 Memory L1 或 legacy truncation
        if context.messages:
            if self._memory:
                context.messages = self._memory.apply_l1(context.messages)
            else:
                context.messages = self._truncation.truncate(context.messages)
        
        return context

    def build_with_compaction(self, current_step: int) -> ChatRequest:
        """
        构建上下文并执行 L1 + L2

        先调用 build()（含 L1 截断），再调用 memory.apply_l2() 执行微折叠。
        若未配置 memory 则等同于 build()。

        Args:
            current_step: 当前 react loop 的 iteration 索引

        Returns:
            ChatRequest: 经过 L1 + L2 处理的请求
        """
        context = self.build()
        if self._memory and context.messages:
            context.messages = self._memory.apply_l2(
                context.messages, current_step
            )
        return context
    
    def build_without_truncation(self) -> ChatRequest:
        """
        构建上下文但不应用任何截断/memory 策略
        
        用于调试或需要完整上下文的场景。
        
        Returns:
            ChatRequest: 未截断的完整请求
        """
        if self._task_input is None:
            raise ValueError("task_input is not set. Call reset() first.")
        
        merged_tools = self.get_all_tools()
        
        return self._strategy.build_context(
            task_input=self._task_input,
            events=self._events,
            environment_states=self._environment_states,
            system_prompt=self._current_system_prompt,
            tools=merged_tools
        )
    
    # ========================================================================
    # 状态查询方法
    # ========================================================================
    
    def get_event_count(self) -> int:
        """获取当前事件数量"""
        return len(self._events)
    
    def get_events_by_type(self, event_type: str) -> List[Event]:
        """
        按类型获取事件
        
        Args:
            event_type: 事件类型（如 "tool_call", "reasoning" 等）
        
        Returns:
            匹配类型的事件列表
        """
        return [e for e in self._events if e.event_type == event_type]
    
    def has_environment(self, key: str) -> bool:
        """检查是否存在指定的环境状态"""
        return key in self._environment_states
    
    def get_environment(self, key: str) -> Optional[EnvironmentState]:
        """
        获取指定的环境状态
        
        Args:
            key: 环境状态的唯一标识
        
        Returns:
            环境状态，不存在时返回 None
        """
        return self._environment_states.get(key)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将当前状态转换为字典（用于调试/序列化）
        
        Returns:
            包含所有状态信息的字典
        """
        all_tools = self.get_all_tools()
        return {
            "task_input": self._task_input.session_id if self._task_input else None,
            "task_id": self._task_input.task_id if self._task_input else None,
            "event_count": len(self._events),
            "environment_states": list(self._environment_states.keys()),
            "system_prompt_length": len(self._current_system_prompt),
            "tools_count": len(all_tools) if all_tools else 0,
            "skill_tools_count": len(self._skill_tools),
        }

