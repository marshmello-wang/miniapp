"""
Memory 系统配置 - L1/L2 的全部配置 dataclass
"""
from dataclasses import dataclass, field
from typing import List, Literal, Optional


@dataclass
class CollapseStrategyConfig:
    """
    单项折叠策略配置

    Attributes:
        type: 折叠类型
            - none: 不折叠
            - remove: 完全移除
            - empty_str: 保留占位但内容清空
            - prefix: 保留前 collapse_prefix_length 个字符
            - prefix_ref: 保留前缀并将完整内容存入外部存储，生成 ref_id
        collapse_prefix_length: prefix / prefix_ref 模式下保留的字符数
    """
    type: Literal["none", "remove", "empty_str", "prefix", "prefix_ref"] = "none"
    collapse_prefix_length: int = 200


@dataclass
class HistoryCollapseConfig:
    """
    历史上下文折叠配置 - 控制 thinking / tool_call / tool_response 的折叠策略

    Attributes:
        thinking_collapse: thinking 折叠策略（支持全部 5 种 type）
        tool_call_collapse: tool_call 折叠策略（仅支持 none / remove）
        tool_response_collapse: tool_response 折叠策略（支持全部 5 种 type）
    """
    thinking_collapse: CollapseStrategyConfig = field(
        default_factory=lambda: CollapseStrategyConfig(type="remove")
    )
    tool_call_collapse: CollapseStrategyConfig = field(
        default_factory=lambda: CollapseStrategyConfig(type="none")
    )
    tool_response_collapse: CollapseStrategyConfig = field(
        default_factory=lambda: CollapseStrategyConfig(type="prefix", collapse_prefix_length=200)
    )

    def __post_init__(self):
        if self.tool_call_collapse.type not in ("none", "remove"):
            raise ValueError(
                f"tool_call_collapse.type must be 'none' or 'remove', "
                f"got '{self.tool_call_collapse.type}'"
            )


@dataclass
class AllocationBudgetConfig:
    """
    上下文 Budget 分配配置

    以 128k 总上下文为例的默认分配：
        128k = 4k(SP) + 4k(memory) + 94k(history) + 10k(react_stack) + 16k(final_output)

    max_history 由计算得出：max_total - system_prompt - memory - react_stack_reserve - final_output_reserve
    """
    max_total_tokens: int = 128000
    system_prompt_tokens: int = 4000
    memory_tokens: int = 4000
    react_stack_reserve: int = 10000
    final_output_reserve: int = 16000

    @property
    def max_history_tokens(self) -> int:
        return (
            self.max_total_tokens
            - self.system_prompt_tokens
            - self.memory_tokens
            - self.react_stack_reserve
            - self.final_output_reserve
        )

    def __post_init__(self):
        if self.max_history_tokens <= 0:
            raise ValueError(
                f"Budget 分配后 max_history_tokens <= 0 "
                f"({self.max_total_tokens} - {self.system_prompt_tokens} - "
                f"{self.memory_tokens} - {self.react_stack_reserve} - "
                f"{self.final_output_reserve} = {self.max_history_tokens})"
            )


@dataclass
class L1Config:
    """
    L1: Allocation Budget + History Context Collapse 配置

    Attributes:
        budget: 上下文 budget 分配
        history_collapse: 历史消息折叠策略
        tool_call_collapse_whitelist: 不折叠 tool_call 的工具名白名单
        tool_response_collapse_whitelist: 不折叠 tool_response 的工具名白名单
    """
    budget: AllocationBudgetConfig = field(default_factory=AllocationBudgetConfig)
    history_collapse: HistoryCollapseConfig = field(default_factory=HistoryCollapseConfig)
    tool_call_collapse_whitelist: List[str] = field(default_factory=list)
    tool_response_collapse_whitelist: List[str] = field(default_factory=list)


@dataclass
class L2Config:
    """
    L2: Micro-Compaction 配置

    在 react loop 内的轻量压缩，无 LLM 操作，同步完成。

    Attributes:
        history_collapse: 折叠策略（可以与 L1 不同）
        after_collapse_max_length: 压缩后的最大 token 数
        tool_call_collapse_whitelist: 不折叠 tool_call 的工具名白名单
        tool_response_collapse_whitelist: 不折叠 tool_response 的工具名白名单
        protected_steps: 保护最近 N 步不被折叠
        fallback_strategy: 折叠后仍超长时的兜底策略
            - abandon: 强制从前往后成对丢弃
            - compress: 不丢弃，标记触发异步 L3
        max_round: 最大 react 轮次（可选兜底）
    """
    history_collapse: HistoryCollapseConfig = field(default_factory=HistoryCollapseConfig)
    after_collapse_max_length: int = 94000
    tool_call_collapse_whitelist: List[str] = field(default_factory=list)
    tool_response_collapse_whitelist: List[str] = field(default_factory=list)
    protected_steps: int = 1
    fallback_strategy: Literal["abandon", "compress"] = "abandon"
    max_round: Optional[int] = None

    def __post_init__(self):
        if self.protected_steps < 0:
            raise ValueError("protected_steps must be >= 0")
        if self.after_collapse_max_length <= 0:
            raise ValueError("after_collapse_max_length must be positive")


@dataclass
class MemoryConfig:
    """
    Memory 系统顶层配置

    Attributes:
        l1: L1 配置（必填）
        l2: L2 配置（可选，不配置则不启用微折叠）
    """
    l1: L1Config = field(default_factory=L1Config)
    l2: Optional[L2Config] = None
