"""
Memory 模块 - L1/L2 上下文记忆管理

提供基于 budget 分配和微折叠的上下文截断能力，
作为 ContextBuilder 的直接集成组件。

Example:
    >>> from common.agent_framework.context_strategy.memory import (
    ...     ContextMemoryHelper, MemoryConfig, L1Config, L2Config,
    ... )
    >>> config = MemoryConfig(l1=L1Config(), l2=L2Config())
    >>> helper = ContextMemoryHelper(config)
    >>> truncated = helper.apply_l1(messages)
    >>> compacted = helper.apply_l2(truncated, current_step=3)
"""

from .config import (
    AllocationBudgetConfig,
    CollapseStrategyConfig,
    HistoryCollapseConfig,
    L1Config,
    L2Config,
    MemoryConfig,
)
from .helper import ContextMemoryHelper
from .store import ExpiredContentStore, InMemoryStore

__all__ = [
    # 配置
    "MemoryConfig",
    "L1Config",
    "L2Config",
    "AllocationBudgetConfig",
    "HistoryCollapseConfig",
    "CollapseStrategyConfig",
    # Helper
    "ContextMemoryHelper",
    # Store
    "ExpiredContentStore",
    "InMemoryStore",
]
