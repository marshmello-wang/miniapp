"""
StateGraph 定义 - 基于状态机的图编排模型

提供节点(Node)、边(Edge)和状态图(StateGraph)的定义，
支持将多个 ReactAgent 和 Python 函数节点编排为完整的状态机。

Example:
    >>> graph = StateGraph()
    >>> graph.add_node("step1", lambda state: {"result": "done"})
    >>> graph.set_entry_point("step1")
    >>> graph.set_finish_point("step1")
    >>> compiled = graph.compile()
"""
import asyncio
import inspect
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, List, Optional, Protocol, Set, Union,
    runtime_checkable,
)
from uuid import uuid4

from common.agent_framework.user_interface.events import Event
from common.agent_framework.user_interface.inputs import TaskInput
from common.agent_framework.user_interface.content_blocks import TextBlock

START = "__start__"
END = "__end__"


# ============================================================================
# 节点执行上下文与结果
# ============================================================================

@dataclass
class NodeContext:
    """传给节点的执行上下文"""
    session_id: str
    task_id: str
    node_name: str
    execution_count: int


@dataclass
class NodeResult:
    """节点执行结果"""
    state_updates: Dict[str, Any] = field(default_factory=dict)
    events: List[Event] = field(default_factory=list)


# ============================================================================
# 节点协议与内置实现
# ============================================================================

@runtime_checkable
class NodeProtocol(Protocol):
    """节点协议 - 所有自定义节点需满足此接口"""

    @property
    def name(self) -> str: ...

    async def execute(self, state: Dict[str, Any], context: NodeContext) -> NodeResult: ...


class AgentNode:
    """
    Agent 节点 - 包装一个 ReactAgent 作为图节点

    Args:
        name: 节点名称
        agent: ReactAgent 实例
        input_mapper: 从共享 state 构建 TaskInput 的函数
        output_key: agent 最终文本输出写入 state 的 key
    """

    def __init__(
        self,
        name: str,
        agent: Any,
        input_mapper: Callable[[Dict[str, Any]], TaskInput],
        output_key: str = "last_agent_output",
    ):
        self._name = name
        self._agent = agent
        self._input_mapper = input_mapper
        self._output_key = output_key

    @property
    def name(self) -> str:
        return self._name

    async def execute(self, state: Dict[str, Any], context: NodeContext) -> NodeResult:
        task_input = self._input_mapper(state)
        events: List[Event] = []
        final_text_parts: List[str] = []

        if hasattr(self._agent, "run_async"):
            async for event in self._agent.run_async(task_input):
                events.append(event)
                if event.event_type == "reasoning":
                    for block in event.content:
                        if isinstance(block, TextBlock) and block.text:
                            final_text_parts.append(block.text)
        else:
            for event in self._agent.run(task_input):
                events.append(event)
                if event.event_type == "reasoning":
                    for block in event.content:
                        if isinstance(block, TextBlock) and block.text:
                            final_text_parts.append(block.text)

        state_updates = {self._output_key: "\n".join(final_text_parts)} if final_text_parts else {}
        return NodeResult(state_updates=state_updates, events=events)


class FunctionNode:
    """
    函数节点 - 包装一个 Python callable 作为图节点

    func 签名: (state: Dict[str, Any]) -> Dict[str, Any]
    返回值为 state 的增量更新。同时支持同步和 async 函数。
    """

    def __init__(self, name: str, func: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self._name = name
        self._func = func

    @property
    def name(self) -> str:
        return self._name

    async def execute(self, state: Dict[str, Any], context: NodeContext) -> NodeResult:
        if inspect.iscoroutinefunction(self._func):
            updates = await self._func(state)
        else:
            updates = self._func(state)
        if updates is None:
            updates = {}
        return NodeResult(state_updates=updates)


# ============================================================================
# 边定义
# ============================================================================

@dataclass
class Edge:
    """普通边"""
    source: str
    target: str


@dataclass
class ConditionalEdge:
    """
    条件边 - 根据 router 函数返回的 key 决定下一步走向

    router: 接收 state，返回路由 key (str)
    path_map: 路由 key -> 目标节点名称 的映射。
              如果为 None，则 router 直接返回目标节点名称。
    """
    source: str
    router: Callable[[Dict[str, Any]], str]
    path_map: Optional[Dict[str, str]] = None


# ============================================================================
# StateGraph: 图定义（用户面向的构建器）
# ============================================================================

class StateGraph:
    """
    状态图定义

    提供链式 API 来构建编排图，最终通过 compile() 转换为可执行的 CompiledGraph。

    Example:
        >>> graph = StateGraph()
        >>> graph.add_node("planner", planner_agent_node)
        >>> graph.add_node("check", lambda s: {"route": "done"})
        >>> graph.set_entry_point("planner")
        >>> graph.add_edge("planner", "check")
        >>> graph.add_conditional_edges("check", lambda s: s["route"], {"done": END})
        >>> compiled = graph.compile()
    """

    def __init__(self, initial_state: Optional[Dict[str, Any]] = None):
        self._nodes: Dict[str, NodeProtocol] = {}
        self._edges: List[Edge] = []
        self._conditional_edges: List[ConditionalEdge] = []
        self._entry_point: Optional[str] = None
        self._finish_points: Set[str] = set()
        self._initial_state = initial_state or {}

    def add_node(
        self,
        name: str,
        node: Union[NodeProtocol, Callable[[Dict[str, Any]], Dict[str, Any]]],
    ) -> "StateGraph":
        if name in (START, END):
            raise ValueError(f"Cannot use reserved name '{name}' as node name")
        if name in self._nodes:
            raise ValueError(f"Node '{name}' already exists")

        if isinstance(node, NodeProtocol):
            self._nodes[name] = node
        elif callable(node):
            self._nodes[name] = FunctionNode(name=name, func=node)
        else:
            raise TypeError(f"node must be a NodeProtocol or callable, got {type(node)}")
        return self

    def add_edge(self, source: str, target: str) -> "StateGraph":
        self._edges.append(Edge(source=source, target=target))
        if source == START and self._entry_point is None:
            self._entry_point = target
        if target == END:
            self._finish_points.add(source)
        return self

    def add_conditional_edges(
        self,
        source: str,
        router: Callable[[Dict[str, Any]], str],
        path_map: Optional[Dict[str, str]] = None,
    ) -> "StateGraph":
        self._conditional_edges.append(ConditionalEdge(
            source=source,
            router=router,
            path_map=path_map,
        ))
        return self

    def set_entry_point(self, name: str) -> "StateGraph":
        self._entry_point = name
        self._edges.append(Edge(source=START, target=name))
        return self

    def set_finish_point(self, name: str) -> "StateGraph":
        self._finish_points.add(name)
        self._edges.append(Edge(source=name, target=END))
        return self

    def compile(self) -> "CompiledGraph":
        if self._entry_point is None:
            raise ValueError("No entry point set. Use set_entry_point() or add_edge(START, ...)")

        if self._entry_point not in self._nodes:
            raise ValueError(f"Entry point '{self._entry_point}' is not a registered node")

        for edge in self._edges:
            if edge.source not in (START,) and edge.source not in self._nodes:
                raise ValueError(f"Edge source '{edge.source}' is not a registered node")
            if edge.target not in (END,) and edge.target not in self._nodes:
                raise ValueError(f"Edge target '{edge.target}' is not a registered node")

        for ce in self._conditional_edges:
            if ce.source not in self._nodes:
                raise ValueError(
                    f"Conditional edge source '{ce.source}' is not a registered node"
                )

        adjacency: Dict[str, List[str]] = {}
        for edge in self._edges:
            if edge.source == START:
                continue
            adjacency.setdefault(edge.source, []).append(edge.target)

        conditional_map: Dict[str, ConditionalEdge] = {}
        for ce in self._conditional_edges:
            if ce.source in conditional_map:
                raise ValueError(
                    f"Node '{ce.source}' already has a conditional edge"
                )
            conditional_map[ce.source] = ce

        return CompiledGraph(
            nodes=dict(self._nodes),
            adjacency=adjacency,
            conditional_edges=conditional_map,
            entry_point=self._entry_point,
            finish_points=set(self._finish_points),
            initial_state=dict(self._initial_state),
        )


# ============================================================================
# CompiledGraph: 编译后的可执行图
# ============================================================================

class CompiledGraph:
    """
    编译后的图 - 由 StateGraph.compile() 产出，不可修改

    提供 get_next_node() 方法用于运行时路由。
    """

    def __init__(
        self,
        nodes: Dict[str, NodeProtocol],
        adjacency: Dict[str, List[str]],
        conditional_edges: Dict[str, ConditionalEdge],
        entry_point: str,
        finish_points: Set[str],
        initial_state: Dict[str, Any],
    ):
        self.nodes = nodes
        self.adjacency = adjacency
        self.conditional_edges = conditional_edges
        self.entry_point = entry_point
        self.finish_points = finish_points
        self.initial_state = initial_state

    def get_node(self, name: str) -> NodeProtocol:
        node = self.nodes.get(name)
        if node is None:
            raise ValueError(f"Node '{name}' not found in graph")
        return node

    def get_next_node(self, current_node: str, state: Dict[str, Any]) -> str:
        """
        根据当前节点和状态，决定下一个要执行的节点。

        优先级：条件边 > 普通边。
        返回 END 表示图执行结束。
        """
        if current_node in self.conditional_edges:
            ce = self.conditional_edges[current_node]
            route_key = ce.router(state)
            if ce.path_map is not None:
                target = ce.path_map.get(route_key)
                if target is None:
                    raise ValueError(
                        f"Router for '{current_node}' returned '{route_key}', "
                        f"which is not in path_map {list(ce.path_map.keys())}"
                    )
                return target
            return route_key

        targets = self.adjacency.get(current_node, [])
        if not targets:
            return END
        if len(targets) > 1:
            raise ValueError(
                f"Node '{current_node}' has multiple outgoing edges {targets} "
                f"but no conditional edge to disambiguate. Use add_conditional_edges()."
            )
        return targets[0]
