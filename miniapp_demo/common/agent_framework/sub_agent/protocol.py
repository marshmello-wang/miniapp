"""
Sub Agent 协议定义 - 核心数据结构
"""
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class SubAgentDefinition:
    """
    子 Agent 定义

    Attributes:
        name: 子 Agent 唯一标识（模型通过此名称调用）
        description: 简短描述（展示在 system prompt 的候选列表中）
        agent: Agent 实例（ReactAgent 或任何实现 run/run_async 的对象）
    """
    name: str
    description: str
    agent: Any


@dataclass
class SubAgentResult:
    """
    子 Agent 执行结果

    Attributes:
        success: 是否成功
        output: 子 Agent 的最终文本输出
        error: 失败时的错误信息
        agent_name: 执行的子 Agent 名称
    """
    success: bool
    output: str = ""
    error: Optional[str] = None
    agent_name: str = ""
