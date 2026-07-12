"""
Sub Agent 模块 - 为 Agent 提供子 Agent 派遣能力

开发者预注册多个子 Agent（name + description + agent 实例），
子 Agent 列表注入 system prompt，模型通过统一的 create_sub_agent 工具按名派遣。
"""

from .protocol import SubAgentDefinition, SubAgentResult
from .registry import SubAgentRegistry
from .manager import SubAgentManager

__all__ = [
    "SubAgentDefinition",
    "SubAgentResult",
    "SubAgentRegistry",
    "SubAgentManager",
]
