"""
L1: Allocation Budget + History Context Collapse

在首次构建上下文时执行：
1. 根据 AllocationBudgetConfig 计算 max_history_tokens
2. 从消息列表中识别 system prompt 和 history 部分
3. 按 User 消息切分为用户轮次（user-round）
4. 对非最近轮次应用折叠策略（折叠先于截断）
5. 折叠后从前往后逐轮丢弃，直到总 token 数在 budget 内
"""
from copy import deepcopy
from typing import List, Optional, Set

from common.llm import Message as LLMMessage

from .collapse import collapse_messages
from .config import L1Config
from .store import ExpiredContentStore
from .token_utils import estimate_messages_tokens


class L1AllocationBudget:
    """
    L1 截断：Budget 分配 + 历史上下文折叠

    处理流程:
        1. 分离 system prompt 消息和 history 消息
        2. 将 history 按 User 消息切分为用户轮次
        3. 对非最近一轮的消息应用折叠（折叠先于截断，使折叠后的消息有更多机会被保留）
        4. 从前往后逐轮丢弃，直到总 token 数在 budget 内
        5. 如果只剩最后一轮仍超 budget，对 User 消息保留后半部分截断
    """

    def __init__(
        self,
        config: L1Config,
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

    def truncate(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """
        执行 L1 截断

        Args:
            messages: 完整消息列表（包含 system prompt）

        Returns:
            截断并折叠后的消息列表
        """
        if not messages:
            return []

        system_messages, history_messages = self._split_system_and_history(messages)

        if not history_messages:
            return system_messages

        rounds = self._split_into_rounds(history_messages)

        if not rounds:
            return system_messages

        # 先折叠非最近轮的消息，再判断是否需要截断
        for i in range(len(rounds) - 1):
            rounds[i] = self._collapse_round(rounds[i])

        max_history = self._config.budget.max_history_tokens

        # 从前往后逐轮丢弃，直到总 token 数在 budget 内
        while len(rounds) > 1 and self._rounds_tokens(rounds) > max_history:
            rounds.pop(0)

        # 如果只剩最后一轮仍超 budget，对 User 消息保留后半部分
        if rounds and self._rounds_tokens(rounds) > max_history:
            self._truncate_round_user(rounds[0], max_history)

        return system_messages + self._flatten_rounds(rounds)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _split_system_and_history(
        self, messages: List[LLMMessage]
    ) -> tuple:
        """分离 system prompt 消息和 history 消息"""
        system_msgs: List[LLMMessage] = []
        history_start = 0

        for i, msg in enumerate(messages):
            if msg.role == "system":
                system_msgs.append(msg)
                history_start = i + 1
            else:
                break

        return system_msgs, messages[history_start:]

    @staticmethod
    def _split_into_rounds(
        history: List[LLMMessage],
    ) -> List[List[LLMMessage]]:
        """
        按 User 消息将 history 切分为用户轮次

        每轮 = User 消息 + 其后续所有 Assistant/Tool 消息。
        开头的孤儿 Assistant/Tool 消息（无前置 User）会被丢弃，
        确保结果始终以 User 消息开头。

        Example:
            [U, A, T, A, U, A, T, A, U, A] -> [[U,A,T,A], [U,A,T,A], [U,A]]
        """
        rounds: List[List[LLMMessage]] = []
        current: List[LLMMessage] = []

        for msg in history:
            if msg.role == "user":
                if current and current[0].role == "user":
                    rounds.append(current)
                current = [msg]
            else:
                current.append(msg)

        if current and current[0].role == "user":
            rounds.append(current)

        return rounds

    def _collapse_round(
        self, round_msgs: List[LLMMessage]
    ) -> List[LLMMessage]:
        """对一个轮次内的所有消息应用折叠"""
        return collapse_messages(
            round_msgs,
            config=self._config.history_collapse,
            store=self._store,
            tc_whitelist=self._tc_whitelist,
            tr_whitelist=self._tr_whitelist,
        )

    @staticmethod
    def _rounds_tokens(rounds: List[List[LLMMessage]]) -> int:
        """计算所有轮次的总 token 数"""
        return sum(estimate_messages_tokens(r) for r in rounds)

    @staticmethod
    def _flatten_rounds(rounds: List[List[LLMMessage]]) -> List[LLMMessage]:
        """将轮次列表展平为消息列表"""
        result: List[LLMMessage] = []
        for r in rounds:
            result.extend(r)
        return result

    @staticmethod
    def _truncate_round_user(
        round_msgs: List[LLMMessage], max_tokens: int
    ) -> None:
        """
        对轮次中的 User 消息保留后半部分截断（原地修改）

        当最后一轮仍超出 budget 时，截断 User 消息的 content。
        """
        if not round_msgs or round_msgs[0].role != "user":
            return

        user_msg = round_msgs[0]
        content = user_msg.content
        if not isinstance(content, str):
            return

        chars_budget = int(max_tokens * 3.0)
        if len(content) <= chars_budget:
            return

        new_msg = deepcopy(user_msg)
        new_msg.content = "...\n" + content[-chars_budget:]
        round_msgs[0] = new_msg
