"""
干预接口定义 - 定义 React Agent 执行过程中的干预钩子
"""
from dataclasses import dataclass, field
from typing import Protocol, Dict, List, Any, Optional, Literal
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.agent_framework.user_interface.inputs import TaskInput
from common.agent_framework.user_interface.events import Event
from common.agent_framework.tool_adapter.protocol import ToolResult
from common.llm import ChatResponse


# ============================================================================
# 干预上下文
# ============================================================================

@dataclass
class HookContext:
    """
    干预上下文 - 传递给 hook 的信息
    
    Attributes:
        phase: 当前阶段
            - "before_reasoning": 推理前
            - "after_reasoning": 推理后
            - "before_tool_execution": 工具执行前
            - "after_tool_execution": 工具执行后
        iteration: 当前迭代次数（从 0 开始）
        task_input: 原始任务输入
        events: 当前已产生的所有事件列表
        current_response: 当前模型响应（仅在 after_reasoning 和 tool 相关阶段可用）
        current_tool_name: 当前工具名称（仅在 tool 相关阶段可用）
        current_tool_result: 当前工具执行结果（仅在 after_tool_execution 阶段可用）
        extra_data: 钩子间传递的额外数据
    
    Example:
        >>> def before_reasoning(self, ctx: HookContext) -> HookResult:
        ...     print(f"Iteration {ctx.iteration}, events so far: {len(ctx.events)}")
        ...     return HookResult()
    """
    phase: Literal[
        "before_reasoning",
        "after_reasoning", 
        "before_tool_execution",
        "after_tool_execution"
    ]
    iteration: int
    task_input: TaskInput
    events: List[Event]
    current_response: Optional[ChatResponse] = None
    current_tool_name: Optional[str] = None
    current_tool_result: Optional[ToolResult] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 干预结果
# ============================================================================

@dataclass
class HookResult:
    """
    干预结果 - hook 返回的指令
    
    Attributes:
        skip_phase: 是否跳过当前阶段（默认 False）
            - before_reasoning 阶段设置为 True：跳过本次推理，直接进入下一轮
            - before_tool_execution 阶段设置为 True：跳过本次工具执行
        inject_prompt: 注入的额外 prompt（会被追加到 system prompt 末尾）
        force_stop: 是否强制停止循环（默认 False）
        modify_tool_params: 修改工具参数（仅 before_tool_execution 阶段有效）
        extra_data: 扩展数据（用于未来扩展，如自定义命令）
    
    Example:
        >>> # 注入额外的指令
        >>> return HookResult(inject_prompt="Remember to be concise.")
        >>> 
        >>> # 强制停止循环
        >>> return HookResult(force_stop=True)
        >>> 
        >>> # 跳过当前工具执行
        >>> return HookResult(skip_phase=True)
    """
    skip_phase: bool = False
    inject_prompt: Optional[str] = None
    force_stop: bool = False
    modify_tool_params: Optional[Dict[str, Any]] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def continue_execution(cls) -> "HookResult":
        """继续正常执行"""
        return cls()
    
    @classmethod
    def stop(cls) -> "HookResult":
        """强制停止"""
        return cls(force_stop=True)
    
    @classmethod
    def skip(cls) -> "HookResult":
        """跳过当前阶段"""
        return cls(skip_phase=True)


# ============================================================================
# Hook 协议
# ============================================================================

class Hook(Protocol):
    """
    干预钩子协议
    
    在 ReactAgent 执行的关键节点提供干预能力。
    
    实现此协议的类可以：
    - 监控执行过程
    - 注入额外指令
    - 修改工具参数
    - 强制停止或跳过某些阶段
    
    Example:
        >>> class LoggingHook:
        ...     def before_reasoning(self, ctx: HookContext) -> HookResult:
        ...         print(f"[Iteration {ctx.iteration}] Starting reasoning...")
        ...         return HookResult()
        ...     
        ...     def after_reasoning(self, ctx: HookContext) -> HookResult:
        ...         if ctx.current_response:
        ...             print(f"Model output: {ctx.current_response.content[:100] if ctx.current_response.content else ''}")
        ...         return HookResult()
        ...     
        ...     def before_tool_execution(self, ctx: HookContext) -> HookResult:
        ...         print(f"Executing tool: {ctx.current_tool_name}")
        ...         return HookResult()
        ...     
        ...     def after_tool_execution(self, ctx: HookContext) -> HookResult:
        ...         if ctx.current_tool_result:
        ...             print(f"Tool result: success={ctx.current_tool_result.success}")
        ...         return HookResult()
    """
    
    def before_reasoning(self, ctx: HookContext) -> HookResult:
        """
        推理前钩子
        
        在每次调用模型进行推理之前触发。
        
        Args:
            ctx: 干预上下文
        
        Returns:
            HookResult: 干预结果
                - force_stop=True: 立即停止整个循环
                - skip_phase=True: 跳过本次推理，进入下一轮迭代
                - inject_prompt: 为本次推理注入额外指令
        """
        ...
    
    def after_reasoning(self, ctx: HookContext) -> HookResult:
        """
        推理后钩子
        
        在模型返回响应后、处理响应内容前触发。
        
        Args:
            ctx: 干预上下文（ctx.current_response 包含模型响应）
        
        Returns:
            HookResult: 干预结果
                - force_stop=True: 立即停止整个循环
        """
        ...
    
    def before_tool_execution(self, ctx: HookContext) -> HookResult:
        """
        工具执行前钩子
        
        在执行每个工具调用之前触发。
        
        Args:
            ctx: 干预上下文（ctx.current_tool_name 包含工具名称）
        
        Returns:
            HookResult: 干预结果
                - skip_phase=True: 跳过本次工具执行
                - modify_tool_params: 修改工具参数
        """
        ...
    
    def after_tool_execution(self, ctx: HookContext) -> HookResult:
        """
        工具执行后钩子
        
        在工具执行完成后触发。
        
        Args:
            ctx: 干预上下文（ctx.current_tool_result 包含执行结果）
        
        Returns:
            HookResult: 干预结果
                - force_stop=True: 立即停止整个循环
        """
        ...


# ============================================================================
# 默认 Hook 实现
# ============================================================================

class DefaultHook:
    """
    默认 Hook 实现 - 所有方法都返回继续执行
    
    可以继承此类并只覆盖需要的方法。
    
    Example:
        >>> class MyHook(DefaultHook):
        ...     def before_reasoning(self, ctx: HookContext) -> HookResult:
        ...         # 只实现需要的钩子
        ...         print(f"Iteration {ctx.iteration}")
        ...         return super().before_reasoning(ctx)
    """
    
    def before_reasoning(self, ctx: HookContext) -> HookResult:
        """默认：继续执行"""
        return HookResult.continue_execution()
    
    def after_reasoning(self, ctx: HookContext) -> HookResult:
        """默认：继续执行"""
        return HookResult.continue_execution()
    
    def before_tool_execution(self, ctx: HookContext) -> HookResult:
        """默认：继续执行"""
        return HookResult.continue_execution()
    
    def after_tool_execution(self, ctx: HookContext) -> HookResult:
        """默认：继续执行"""
        return HookResult.continue_execution()


class CompositeHook:
    """
    组合 Hook - 将多个 Hook 组合在一起
    
    按顺序执行所有 Hook，如果任何一个返回 force_stop 或 skip_phase，
    则立即返回该结果，不再执行后续 Hook。
    
    inject_prompt 会被累积合并。
    
    Example:
        >>> hook = CompositeHook([LoggingHook(), ValidationHook()])
        >>> config = ReactAgentConfig(..., hooks=[hook])
    """
    
    def __init__(self, hooks: List[Hook]):
        """
        初始化组合 Hook
        
        Args:
            hooks: Hook 列表，按顺序执行
        """
        self._hooks = hooks
    
    def _merge_results(self, results: List[HookResult]) -> HookResult:
        """合并多个 HookResult"""
        merged = HookResult()
        inject_prompts = []
        
        for result in results:
            if result.force_stop:
                merged.force_stop = True
                break
            if result.skip_phase:
                merged.skip_phase = True
                break
            if result.inject_prompt:
                inject_prompts.append(result.inject_prompt)
            if result.modify_tool_params:
                if merged.modify_tool_params is None:
                    merged.modify_tool_params = {}
                merged.modify_tool_params.update(result.modify_tool_params)
            merged.extra_data.update(result.extra_data)
        
        if inject_prompts:
            merged.inject_prompt = "\n".join(inject_prompts)
        
        return merged
    
    def before_reasoning(self, ctx: HookContext) -> HookResult:
        """执行所有 Hook 的 before_reasoning"""
        results = []
        for hook in self._hooks:
            result = hook.before_reasoning(ctx)
            results.append(result)
            if result.force_stop or result.skip_phase:
                break
        return self._merge_results(results)
    
    def after_reasoning(self, ctx: HookContext) -> HookResult:
        """执行所有 Hook 的 after_reasoning"""
        results = []
        for hook in self._hooks:
            result = hook.after_reasoning(ctx)
            results.append(result)
            if result.force_stop:
                break
        return self._merge_results(results)
    
    def before_tool_execution(self, ctx: HookContext) -> HookResult:
        """执行所有 Hook 的 before_tool_execution"""
        results = []
        for hook in self._hooks:
            result = hook.before_tool_execution(ctx)
            results.append(result)
            if result.force_stop or result.skip_phase:
                break
        return self._merge_results(results)
    
    def after_tool_execution(self, ctx: HookContext) -> HookResult:
        """执行所有 Hook 的 after_tool_execution"""
        results = []
        for hook in self._hooks:
            result = hook.after_tool_execution(ctx)
            results.append(result)
            if result.force_stop:
                break
        return self._merge_results(results)

