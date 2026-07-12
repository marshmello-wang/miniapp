"""
Agent Loop 模块 - 提供 Agent 执行循环的实现

支持：
- ReactAgent: Reasoning-Action 循环模式
- OrchestratorAgent: 基于 StateGraph 的多节点编排执行引擎

Example:
    >>> from agent_loop import create_react_agent, ReactAgentConfig
    >>> from agent_loop import StateGraph, END, OrchestratorAgent, OrchestratorConfig
"""

from .config import ReactAgentConfig, SubAgentConfig
from .hooks import (
    Hook,
    HookContext,
    HookResult,
    DefaultHook,
    CompositeHook
)
from .react_agent import ReactAgent, create_react_agent
from .graph import (
    START,
    END,
    StateGraph,
    CompiledGraph,
    AgentNode,
    FunctionNode,
    NodeContext,
    NodeResult,
    NodeProtocol,
)
from .orchestrator_agent import (
    OrchestratorAgent,
    OrchestratorConfig,
    OrchestratorHook,
    OrchestratorHookContext,
    OrchestratorHookResult,
    DefaultOrchestratorHook,
    create_orchestrator_agent,
)

__all__ = [
    # 配置
    "ReactAgentConfig",
    "SubAgentConfig",
    # ReactAgent Hook
    "Hook",
    "HookContext",
    "HookResult",
    "DefaultHook",
    "CompositeHook",
    # ReactAgent
    "ReactAgent",
    "create_react_agent",
    # Graph 定义
    "START",
    "END",
    "StateGraph",
    "CompiledGraph",
    "AgentNode",
    "FunctionNode",
    "NodeContext",
    "NodeResult",
    "NodeProtocol",
    # OrchestratorAgent
    "OrchestratorAgent",
    "OrchestratorConfig",
    "OrchestratorHook",
    "OrchestratorHookContext",
    "OrchestratorHookResult",
    "DefaultOrchestratorHook",
    "create_orchestrator_agent",
]

