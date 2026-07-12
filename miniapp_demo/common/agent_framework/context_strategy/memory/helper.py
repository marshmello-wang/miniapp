"""
ContextMemoryHelper - L1/L2 Memory 系统的统一入口

作为 ContextBuilder 的直接集成组件，替代原有 TruncationStrategy。
也可独立使用（不依赖 ContextBuilder）。
"""
from typing import List, Optional

from common.llm import Message as LLMMessage

from .config import MemoryConfig
from .l1_budget import L1AllocationBudget
from .l2_compaction import L2MicroCompaction
from .store import ExpiredContentStore


class ContextMemoryHelper:
    """
    Memory 截断 Helper - L1/L2 的统一入口

    L1 (Allocation Budget + History Collapse):
        在构建上下文时执行，负责 budget 分配和历史消息折叠。
        通过 ContextBuilder.build() 自动调用。

    L2 (Micro-Compaction):
        在 react loop 中每轮推理前执行，轻量同步压缩 react stack。
        通过 ContextBuilder.build_with_compaction() 自动调用。

    Example (独立使用):
        >>> from common.agent_framework.context_strategy.memory import (
        ...     ContextMemoryHelper, MemoryConfig, L1Config
        ... )
        >>> config = MemoryConfig(l1=L1Config())
        >>> helper = ContextMemoryHelper(config)
        >>> truncated = helper.apply_l1(messages)

    Example (通过 ContextBuilder):
        >>> builder = ContextBuilder(
        ...     strategy=strategy,
        ...     base_system_prompt=sp,
        ...     memory=helper,
        ... )
        >>> context = builder.build_with_compaction(current_step=3)
    """

    def __init__(
        self,
        config: MemoryConfig,
        store: Optional[ExpiredContentStore] = None,
    ):
        self._config = config
        self._store = store
        self._l1 = L1AllocationBudget(config.l1, store)
        self._l2 = (
            L2MicroCompaction(config.l2, store) if config.l2 else None
        )

    @property
    def config(self) -> MemoryConfig:
        return self._config

    @property
    def store(self) -> Optional[ExpiredContentStore]:
        return self._store

    def apply_l1(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """
        L1: Allocation Budget + History Collapse

        根据 budget 配置截断历史消息，并对保留的历史消息应用折叠策略。
        在 ContextBuilder.build() 中自动调用。

        Args:
            messages: 完整消息列表（含 system prompt）

        Returns:
            截断并折叠后的消息列表
        """
        return self._l1.truncate(messages)

    def apply_l2(
        self, messages: List[LLMMessage], current_step: int
    ) -> List[LLMMessage]:
        """
        L2: Micro-Compaction

        在 react loop 中按需压缩上下文，防止工具结果累积撑爆上下文。
        在 ContextBuilder.build_with_compaction() 中自动调用。

        Args:
            messages: 当前完整消息列表
            current_step: 当前 react loop 的 iteration 索引

        Returns:
            压缩后的消息列表；若未配置 L2 则原样返回
        """
        if not self._l2:
            return messages
        return self._l2.compact(messages, current_step)
