"""
L2: Micro-Compaction（微折叠）

在 react loop 内，每轮 API 调用前执行的轻量同步压缩。
清理不太可能再被引用的旧工具结果，防止工具结果线性积累撑爆上下文。

执行规则:
    1. 估算当前上下文 token 数，检查是否超过 after_collapse_max_length
    2. 如超过：折叠全部历史轮次的 think/tool_call/tool_response
    3. 如仍超过：从前往后折叠当前轮次，保护 protected_steps 最近的步骤
    4. 如仍超过：执行 fallback（abandon 强制丢弃 / compress 标记）
"""
from copy import deepcopy
from typing import List, Optional, Set, Tuple

from common.llm import Message as LLMMessage

from .collapse import collapse_message
from .config import L2Config
from .store import ExpiredContentStore
from .token_utils import estimate_message_tokens, estimate_messages_tokens


class L2MicroCompaction:
    """
    L2 微折叠

    特点:
        - 轻量/即时：无 LLM 操作，同步完成
        - 主要面向 tool call/response，非 tool 的增长依赖 L3 兜底
        - 白名单中的工具不被折叠
        - 保护最近 N 步不被折叠
    """

    def __init__(
        self,
        config: L2Config,
        store: Optional[ExpiredContentStore] = None,
    ):
        self._config = config
        self._store = store
        self._tc_whitelist: Optional[Set[str]] = (
            set(config.tool_call_collapse_whitelist)
            if config.tool_call_collapse_whitelist
            else None
        )
        self._tr_whitelist: Optional[Set[str]] = (
            set(config.tool_response_collapse_whitelist)
            if config.tool_response_collapse_whitelist
            else None
        )

    def compact(
        self, messages: List[LLMMessage], current_step: int
    ) -> List[LLMMessage]:
        """
        执行 L2 微折叠

        Args:
            messages: 当前完整消息列表（含 system prompt）
            current_step: 当前 react loop 的 iteration 索引

        Returns:
            折叠后的消息列表
        """
        total_tokens = estimate_messages_tokens(messages)
        max_len = self._config.after_collapse_max_length

        if total_tokens <= max_len:
            return messages

        # 分离 system 和非 system 消息
        system_msgs, body_msgs = self._split_system(messages)
        system_tokens = estimate_messages_tokens(system_msgs)
        body_budget = max_len - system_tokens

        if body_budget <= 0:
            return messages

        # 识别 history 区域 vs 当前轮次区域
        history_indices, current_indices = self._partition_by_round(
            body_msgs, current_step
        )

        # 阶段 1：折叠全部历史轮次
        body_msgs = self._collapse_indices(body_msgs, history_indices)

        if estimate_messages_tokens(body_msgs) <= body_budget:
            return system_msgs + body_msgs

        # 阶段 2：从前往后折叠当前轮次（保护最近 protected_steps 步）
        protected = self._get_protected_indices(
            body_msgs, current_indices, self._config.protected_steps
        )
        foldable_current = [i for i in current_indices if i not in protected]
        body_msgs = self._collapse_indices(body_msgs, foldable_current)

        if estimate_messages_tokens(body_msgs) <= body_budget:
            return system_msgs + body_msgs

        # 阶段 3：兜底（仅在当前轮次内丢弃，不移除 history 消息）
        if self._config.fallback_strategy == "abandon":
            no_remove = protected | set(history_indices)
            body_msgs = self._abandon_until_fit(body_msgs, body_budget, no_remove)
        # compress 策略不做丢弃，由上层触发异步 L3

        return system_msgs + body_msgs

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _split_system(
        messages: List[LLMMessage],
    ) -> Tuple[List[LLMMessage], List[LLMMessage]]:
        """分离 system 消息和 body 消息"""
        system: List[LLMMessage] = []
        body_start = 0
        for i, msg in enumerate(messages):
            if msg.role == "system":
                system.append(msg)
                body_start = i + 1
            else:
                break
        return system, messages[body_start:]

    @staticmethod
    def _partition_by_round(
        body_msgs: List[LLMMessage], current_step: int
    ) -> Tuple[List[int], List[int]]:
        """
        按轮次划分消息索引

        从消息列表中找到 history（上一个 task 的消息 + 早期 react 轮次）
        和当前轮次的消息。

        使用 user 消息作为轮次分界：最后一个 user 消息之后的都属于当前轮次。
        """
        last_user_idx = -1
        for i in range(len(body_msgs) - 1, -1, -1):
            if body_msgs[i].role == "user":
                last_user_idx = i
                break

        if last_user_idx < 0:
            return list(range(len(body_msgs))), []

        history_indices = list(range(last_user_idx))
        current_indices = list(range(last_user_idx, len(body_msgs)))
        return history_indices, current_indices

    def _collapse_indices(
        self, messages: List[LLMMessage], indices: List[int]
    ) -> List[LLMMessage]:
        """对指定索引的消息执行折叠"""
        result = list(messages)
        for i in indices:
            result[i] = collapse_message(
                result[i],
                config=self._config.history_collapse,
                store=self._store,
                tc_whitelist=self._tc_whitelist,
                tr_whitelist=self._tr_whitelist,
            )
        return result

    @staticmethod
    def _get_protected_indices(
        messages: List[LLMMessage],
        current_indices: List[int],
        protected_steps: int,
    ) -> Set[int]:
        """
        计算需要保护的消息索引集合

        从当前轮次区域的末尾向前，保护 protected_steps 步。
        一步 = 一个 assistant 消息及其关联的 tool 消息。
        最后一条 assistant 消息始终被保护。
        """
        if not current_indices or protected_steps <= 0:
            return set()

        protected: Set[int] = set()
        steps_counted = 0

        for i in reversed(current_indices):
            msg = messages[i]
            protected.add(i)
            if msg.role == "assistant":
                steps_counted += 1
                if steps_counted >= protected_steps:
                    break

        return protected

    @staticmethod
    def _abandon_until_fit(
        messages: List[LLMMessage],
        budget: int,
        protected: Set[int],
    ) -> List[LLMMessage]:
        """
        abandon 兜底：从前往后成对丢弃 assistant+tool 消息直到满足 budget

        User 消息永远保留。每个 react step（assistant + 关联 tool 消息）
        作为一个整体丢弃，避免产生孤立消息。
        """
        # 将可丢弃消息按 react step 分组（每步 = assistant + 后续 tool）
        steps: List[List[int]] = []
        current_step: List[int] = []

        for i in range(len(messages)):
            if i in protected or messages[i].role == "user":
                continue
            if messages[i].role == "assistant":
                if current_step:
                    steps.append(current_step)
                current_step = [i]
            else:
                current_step.append(i)

        if current_step:
            steps.append(current_step)

        # 从前往后逐步丢弃，直到满足 budget
        to_remove: Set[int] = set()
        for step_indices in steps:
            to_remove.update(step_indices)
            remaining = [
                messages[j]
                for j in range(len(messages))
                if j not in to_remove
            ]
            if estimate_messages_tokens(remaining) <= budget:
                break

        return [
            messages[i]
            for i in range(len(messages))
            if i not in to_remove
        ]
