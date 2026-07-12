"""
OrchestratorAgent 实现 - 基于 StateGraph 的多节点编排执行引擎

将多个 ReactAgent 和函数节点组织为状态机，按图拓扑依次执行，
节点间通过共享 state 字典传递数据。支持循环、条件分支和重试。

Example:
    >>> from common.agent_framework.agent_loop.graph import StateGraph, END
    >>> graph = StateGraph()
    >>> graph.add_node("step1", lambda s: {"result": "hello"})
    >>> graph.set_entry_point("step1")
    >>> graph.set_finish_point("step1")
    >>> compiled = graph.compile()
    >>>
    >>> config = OrchestratorConfig(graph=compiled)
    >>> agent = OrchestratorAgent(config)
    >>> for event in agent.run(task_input):
    ...     print(event.event_type)
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Protocol
from uuid import uuid4

from common.agent_framework.user_interface.events import Event
from common.agent_framework.user_interface.inputs import TaskInput
from common.agent_framework.user_interface.content_blocks import ContentBlock, TextBlock

from .graph import CompiledGraph, END, NodeContext, NodeResult


# ============================================================================
# Orchestrator Hook
# ============================================================================

@dataclass
class OrchestratorHookContext:
    """编排钩子上下文"""
    node_name: str
    execution_count: int
    state: Dict[str, Any]
    task_input: TaskInput
    events: List[Event]
    node_result: Optional[NodeResult] = None


@dataclass
class OrchestratorHookResult:
    """编排钩子返回值"""
    force_stop: bool = False
    skip_node: bool = False
    state_overrides: Optional[Dict[str, Any]] = None

    @classmethod
    def continue_execution(cls) -> "OrchestratorHookResult":
        return cls()

    @classmethod
    def stop(cls) -> "OrchestratorHookResult":
        return cls(force_stop=True)


class OrchestratorHook(Protocol):
    """
    编排级别钩子协议

    在每个节点执行前后提供干预能力。
    """

    def before_node(self, ctx: OrchestratorHookContext) -> OrchestratorHookResult:
        ...

    def after_node(self, ctx: OrchestratorHookContext) -> OrchestratorHookResult:
        ...


class DefaultOrchestratorHook:
    """默认编排钩子 - 所有方法返回继续执行"""

    def before_node(self, ctx: OrchestratorHookContext) -> OrchestratorHookResult:
        return OrchestratorHookResult.continue_execution()

    def after_node(self, ctx: OrchestratorHookContext) -> OrchestratorHookResult:
        return OrchestratorHookResult.continue_execution()


# ============================================================================
# OrchestratorConfig
# ============================================================================

@dataclass
class OrchestratorConfig:
    """
    OrchestratorAgent 配置

    Attributes:
        graph: 编译后的状态图
        max_node_executions: 最大节点执行次数（防止无限循环），默认 100
        hooks: 编排级别钩子列表
    """
    graph: CompiledGraph
    max_node_executions: int = 100
    hooks: List[OrchestratorHook] = field(default_factory=list)

    def __post_init__(self):
        if self.max_node_executions <= 0:
            raise ValueError("max_node_executions must be positive")


# ============================================================================
# OrchestratorAgent
# ============================================================================

class OrchestratorAgent:
    """
    编排 Agent - 基于状态图执行多节点工作流

    遵循 Agent 协议（run(TaskInput) -> Iterator[Event]）。

    执行流程:
        1. 初始化 state（合并图的 initial_state 和 task_input 信息）
        2. 从 entry_point 开始，依次执行节点
        3. 每个节点执行后更新 state，通过边/条件边确定下一节点
        4. 到达 END 或超过 max_node_executions 时停止

    事件类型:
        - orchestration_start: 编排开始
        - node_start: 节点开始执行
        - node_complete: 节点执行完成
        - orchestration_complete: 编排完成
        - 子 Agent 产生的事件透传（metadata 附加 orchestrator_node）
    """

    def __init__(self, config: OrchestratorConfig):
        self._graph = config.graph
        self._max_executions = config.max_node_executions
        self._hooks = config.hooks or []

    def run(self, task_input: TaskInput) -> Iterator[Event]:
        """同步执行接口"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async_gen = self._run_async(task_input)
            while True:
                try:
                    event = loop.run_until_complete(async_gen.__anext__())
                    yield event
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    async def run_async(self, task_input: TaskInput):
        """异步执行接口"""
        async for event in self._run_async(task_input):
            yield event

    async def _run_async(self, task_input: TaskInput):
        session_id = task_input.session_id
        task_id = task_input.task_id

        state: Dict[str, Any] = {
            **self._graph.initial_state,
            "task_input": task_input,
            "messages": task_input.messages,
            "session_id": session_id,
            "task_id": task_id,
        }

        events: List[Event] = []

        start_event = self._create_event(
            session_id=session_id,
            task_id=task_id,
            event_type="orchestration_start",
            content=[TextBlock(f"Starting orchestration from '{self._graph.entry_point}'")],
            metadata={
                "entry_point": self._graph.entry_point,
                "node_count": len(self._graph.nodes),
            },
        )
        events.append(start_event)
        yield start_event

        current_node = self._graph.entry_point
        execution_count = 0

        while current_node != END and execution_count < self._max_executions:
            node = self._graph.get_node(current_node)

            # ---- before_node hook ----
            hook_ctx = OrchestratorHookContext(
                node_name=current_node,
                execution_count=execution_count,
                state=dict(state),
                task_input=task_input,
                events=list(events),
            )
            hook_result = self._run_hooks_before(hook_ctx)
            if hook_result.force_stop:
                break
            if hook_result.skip_node:
                current_node = self._graph.get_next_node(current_node, state)
                execution_count += 1
                continue
            if hook_result.state_overrides:
                state.update(hook_result.state_overrides)

            # ---- node_start event ----
            node_start_event = self._create_event(
                session_id=session_id,
                task_id=task_id,
                event_type="node_start",
                content=[TextBlock(f"Executing node '{current_node}'")],
                metadata={
                    "node_name": current_node,
                    "execution_count": execution_count,
                },
            )
            events.append(node_start_event)
            yield node_start_event

            # ---- 执行节点 ----
            node_context = NodeContext(
                session_id=session_id,
                task_id=task_id,
                node_name=current_node,
                execution_count=execution_count,
            )

            try:
                result = await node.execute(state, node_context)
            except Exception as e:
                error_event = self._create_event(
                    session_id=session_id,
                    task_id=task_id,
                    event_type="error",
                    content=[TextBlock(f"Node '{current_node}' failed: {str(e)}")],
                    metadata={
                        "node_name": current_node,
                        "error": str(e),
                        "execution_count": execution_count,
                    },
                )
                events.append(error_event)
                yield error_event
                break

            # 透传子节点事件，附加 orchestrator_node 元数据
            for sub_event in result.events:
                if sub_event.metadata is None:
                    sub_event.metadata = {}
                sub_event.metadata["orchestrator_node"] = current_node
                events.append(sub_event)
                yield sub_event

            # 更新 state
            state.update(result.state_updates)

            # ---- node_complete event ----
            node_complete_event = self._create_event(
                session_id=session_id,
                task_id=task_id,
                event_type="node_complete",
                content=[TextBlock(f"Node '{current_node}' completed")],
                metadata={
                    "node_name": current_node,
                    "execution_count": execution_count,
                    "state_updates_keys": list(result.state_updates.keys()),
                },
            )
            events.append(node_complete_event)
            yield node_complete_event

            # ---- after_node hook ----
            hook_ctx = OrchestratorHookContext(
                node_name=current_node,
                execution_count=execution_count,
                state=dict(state),
                task_input=task_input,
                events=list(events),
                node_result=result,
            )
            hook_result = self._run_hooks_after(hook_ctx)
            if hook_result.force_stop:
                break
            if hook_result.state_overrides:
                state.update(hook_result.state_overrides)

            # ---- 路由到下一个节点 ----
            try:
                current_node = self._graph.get_next_node(current_node, state)
            except ValueError as e:
                error_event = self._create_event(
                    session_id=session_id,
                    task_id=task_id,
                    event_type="error",
                    content=[TextBlock(f"Routing error: {str(e)}")],
                    metadata={
                        "node_name": current_node,
                        "error": str(e),
                        "execution_count": execution_count,
                    },
                )
                events.append(error_event)
                yield error_event
                break

            execution_count += 1

        # ---- orchestration_complete event ----
        reason = "completed"
        if execution_count >= self._max_executions and current_node != END:
            reason = "max_node_executions"

        complete_event = self._create_event(
            session_id=session_id,
            task_id=task_id,
            event_type="orchestration_complete",
            content=[],
            metadata={
                "total_executions": execution_count,
                "reason": reason,
                "final_state_keys": list(state.keys()),
            },
        )
        events.append(complete_event)
        yield complete_event

    # ----------------------------------------------------------------
    # 内部辅助
    # ----------------------------------------------------------------

    def _run_hooks_before(self, ctx: OrchestratorHookContext) -> OrchestratorHookResult:
        merged = OrchestratorHookResult()
        for hook in self._hooks:
            result = hook.before_node(ctx)
            if result.force_stop:
                return OrchestratorHookResult(force_stop=True)
            if result.skip_node:
                return OrchestratorHookResult(skip_node=True)
            if result.state_overrides:
                if merged.state_overrides is None:
                    merged.state_overrides = {}
                merged.state_overrides.update(result.state_overrides)
        return merged

    def _run_hooks_after(self, ctx: OrchestratorHookContext) -> OrchestratorHookResult:
        merged = OrchestratorHookResult()
        for hook in self._hooks:
            result = hook.after_node(ctx)
            if result.force_stop:
                return OrchestratorHookResult(force_stop=True)
            if result.state_overrides:
                if merged.state_overrides is None:
                    merged.state_overrides = {}
                merged.state_overrides.update(result.state_overrides)
        return merged

    @staticmethod
    def _create_event(
        session_id: str,
        task_id: str,
        event_type: str,
        content: List[ContentBlock],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        return Event.create(
            event_id=str(uuid4()),
            session_id=session_id,
            task_id=task_id,
            event_type=event_type,
            content=content,
            metadata=metadata,
        )


def create_orchestrator_agent(config: OrchestratorConfig) -> OrchestratorAgent:
    """
    创建 OrchestratorAgent 的工厂函数

    Args:
        config: OrchestratorConfig 配置

    Returns:
        OrchestratorAgent 实例
    """
    return OrchestratorAgent(config)
