"""
Context Strategy 模块

上下文策略模块，负责将用户输入、执行轨迹、环境状态转换为模型可用的上下文。
"""

from .protocol import (
    EnvironmentState,
    ContextStrategy,
)

from .truncation import (
    TruncationStrategy,
    NoTruncation,
    SlidingWindowTruncation,
    MessageCountTruncation,
    TokenEstimateTruncation,
    CompositeTruncation,
)

from .builder import ContextBuilder

from .default_strategy import DefaultContextStrategy

from .memory import (
    ContextMemoryHelper,
    MemoryConfig,
    L1Config,
    L2Config,
    AllocationBudgetConfig,
    HistoryCollapseConfig,
    CollapseStrategyConfig,
    ExpiredContentStore,
    InMemoryStore,
)

__all__ = [
    # Protocol
    "EnvironmentState",
    "ContextStrategy",
    
    # Truncation (legacy)
    "TruncationStrategy",
    "NoTruncation",
    "SlidingWindowTruncation",
    "MessageCountTruncation",
    "TokenEstimateTruncation",
    "CompositeTruncation",
    
    # Builder
    "ContextBuilder",
    
    # Default Implementation
    "DefaultContextStrategy",

    # Memory (L1/L2)
    "ContextMemoryHelper",
    "MemoryConfig",
    "L1Config",
    "L2Config",
    "AllocationBudgetConfig",
    "HistoryCollapseConfig",
    "CollapseStrategyConfig",
    "ExpiredContentStore",
    "InMemoryStore",
]

