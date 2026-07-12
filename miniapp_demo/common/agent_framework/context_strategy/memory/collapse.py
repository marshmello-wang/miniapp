"""
核心折叠逻辑 - L1/L2 共用的 thinking / tool_call / tool_response 折叠操作
"""
from copy import deepcopy
from dataclasses import replace
from typing import List, Optional, Set

from common.llm import Message as LLMMessage

from .config import CollapseStrategyConfig, HistoryCollapseConfig
from .store import ExpiredContentStore


EXPIRE_HINT_TEMPLATE = (
    "{prefix}...[旧内容已被折叠至外部存储，"
    "查看详情需调用 `read_expire_history` 工具，ref_id:{ref_id}]"
)


def _apply_prefix(
    text: str,
    strategy: CollapseStrategyConfig,
    content_type: str,
    store: Optional[ExpiredContentStore],
) -> str:
    """
    对文本应用 prefix / prefix_ref 折叠

    Args:
        text: 原始文本
        strategy: 折叠策略配置
        content_type: 内容类型（"think" / "tool"），用于 ref_id 前缀
        store: 外部存储（prefix_ref 模式必须）

    Returns:
        折叠后的文本
    """
    prefix_len = strategy.collapse_prefix_length
    if len(text) <= prefix_len:
        return text

    prefix = text[:prefix_len]

    if strategy.type == "prefix":
        return prefix + "..."

    # prefix_ref
    if store is None:
        return prefix + "..."

    ref_id = store.save(text, content_type)
    return EXPIRE_HINT_TEMPLATE.format(prefix=prefix, ref_id=ref_id)


def collapse_thinking(
    message: LLMMessage,
    strategy: CollapseStrategyConfig,
    store: Optional[ExpiredContentStore] = None,
) -> LLMMessage:
    """
    折叠 assistant 消息中的 thinking 字段

    策略:
        none      - 不处理
        remove    - 清除 thinking，不保留 <think> 标记
        empty_str - thinking 设为 ""
        prefix    - 保留前 N 个字符
        prefix_ref - 保留前 N 个字符 + 存入外部存储
    """
    if message.role != "assistant" or not message.thinking:
        return message
    if strategy.type == "none":
        return message

    msg = deepcopy(message)

    if strategy.type == "remove":
        msg.thinking = None
    elif strategy.type == "empty_str":
        msg.thinking = ""
    elif strategy.type in ("prefix", "prefix_ref"):
        msg.thinking = _apply_prefix(msg.thinking, strategy, "think", store)
    return msg


def collapse_tool_calls(
    message: LLMMessage,
    strategy: CollapseStrategyConfig,
    whitelist: Optional[Set[str]] = None,
) -> LLMMessage:
    """
    折叠 assistant 消息中的 tool_calls

    策略:
        none   - 不处理
        remove - 移除 tool_calls（白名单中的保留）
    """
    if message.role != "assistant" or not message.tool_calls:
        return message
    if strategy.type == "none":
        return message

    msg = deepcopy(message)

    if strategy.type == "remove":
        if whitelist:
            msg.tool_calls = [
                tc for tc in msg.tool_calls if tc.name in whitelist
            ]
            if not msg.tool_calls:
                msg.tool_calls = None
        else:
            msg.tool_calls = None
    return msg


def collapse_tool_response(
    message: LLMMessage,
    strategy: CollapseStrategyConfig,
    store: Optional[ExpiredContentStore] = None,
    whitelist: Optional[Set[str]] = None,
) -> LLMMessage:
    """
    折叠 tool role 消息的 content

    策略:
        none      - 不处理
        remove    - content 设为 ""
        empty_str - content 设为 ""
        prefix    - content 保留前 N 个字符
        prefix_ref - content 保留前 N 个字符 + 存入外部存储
    """
    if message.role != "tool":
        return message
    if strategy.type == "none":
        return message
    if whitelist and message.name and message.name in whitelist:
        return message

    msg = deepcopy(message)

    content_str = msg.content if isinstance(msg.content, str) else str(msg.content)

    if strategy.type in ("remove", "empty_str"):
        msg.content = ""
    elif strategy.type in ("prefix", "prefix_ref"):
        msg.content = _apply_prefix(content_str, strategy, "tool", store)
    return msg


def collapse_message(
    message: LLMMessage,
    config: HistoryCollapseConfig,
    store: Optional[ExpiredContentStore] = None,
    tc_whitelist: Optional[Set[str]] = None,
    tr_whitelist: Optional[Set[str]] = None,
) -> LLMMessage:
    """
    对单条消息应用完整的折叠配置

    按 thinking -> tool_calls -> tool_response 的顺序依次折叠。

    Args:
        message: 原始消息
        config: 折叠配置
        store: 外部存储（prefix_ref 需要）
        tc_whitelist: tool_call 白名单
        tr_whitelist: tool_response 白名单

    Returns:
        折叠后的消息（新对象，不修改原始消息）
    """
    result = message

    if result.role == "assistant":
        result = collapse_thinking(result, config.thinking_collapse, store)
        result = collapse_tool_calls(result, config.tool_call_collapse, tc_whitelist)
    elif result.role == "tool":
        result = collapse_tool_response(
            result, config.tool_response_collapse, store, tr_whitelist
        )

    return result


def collapse_messages(
    messages: List[LLMMessage],
    config: HistoryCollapseConfig,
    store: Optional[ExpiredContentStore] = None,
    tc_whitelist: Optional[Set[str]] = None,
    tr_whitelist: Optional[Set[str]] = None,
    skip_indices: Optional[Set[int]] = None,
) -> List[LLMMessage]:
    """
    对消息列表批量应用折叠

    Args:
        messages: 消息列表
        config: 折叠配置
        store: 外部存储
        tc_whitelist: tool_call 白名单
        tr_whitelist: tool_response 白名单
        skip_indices: 跳过折叠的消息索引集合（用于保护最近轮次）

    Returns:
        折叠后的消息列表
    """
    result = []
    for i, msg in enumerate(messages):
        if skip_indices and i in skip_indices:
            result.append(msg)
        else:
            result.append(
                collapse_message(msg, config, store, tc_whitelist, tr_whitelist)
            )
    return result
