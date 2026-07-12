"""
Sub Agent 注册中心 - 管理预注册的子 Agent
"""
from typing import Dict, List, Optional, Any

from .protocol import SubAgentDefinition


class SubAgentRegistry:
    """
    子 Agent 注册中心

    管理所有预注册的子 Agent 定义，供 SubAgentManager 和 CreateSubAgentTool 使用。
    """

    def __init__(self):
        self._agents: Dict[str, SubAgentDefinition] = {}

    def register(self, name: str, agent: Any, description: str) -> None:
        """
        注册一个子 Agent

        Args:
            name: 唯一标识
            agent: Agent 实例
            description: 简短描述

        Raises:
            ValueError: 名称已存在
        """
        if name in self._agents:
            raise ValueError(f"Sub agent '{name}' already registered")
        self._agents[name] = SubAgentDefinition(
            name=name,
            description=description,
            agent=agent,
        )

    def register_definition(self, definition: SubAgentDefinition) -> None:
        """直接注册一个 SubAgentDefinition"""
        if definition.name in self._agents:
            raise ValueError(f"Sub agent '{definition.name}' already registered")
        self._agents[definition.name] = definition

    def get(self, name: str) -> Optional[SubAgentDefinition]:
        return self._agents.get(name)

    def list_all(self) -> List[SubAgentDefinition]:
        return list(self._agents.values())

    def has(self, name: str) -> bool:
        return name in self._agents

    def __len__(self) -> int:
        return len(self._agents)
