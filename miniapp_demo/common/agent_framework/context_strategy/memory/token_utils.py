"""
Token 估算工具 - 基于字符数的粗略 token 估算
"""
from typing import List, Union

from common.llm import Message as LLMMessage


def estimate_content_tokens(content, chars_per_token: float = 3.0) -> int:
    """
    估算内容的 token 数

    支持 str 或 List[TextContent/ImageContent/VideoContent] 两种形式。
    """
    if content is None:
        return 0

    total_chars = 0
    if isinstance(content, str):
        total_chars = len(content)
    elif isinstance(content, list):
        for part in content:
            if hasattr(part, "text"):
                total_chars += len(part.text)
            elif hasattr(part, "data"):
                total_chars += int(500 * chars_per_token)
    return max(1, int(total_chars / chars_per_token))


def estimate_message_tokens(message: LLMMessage, chars_per_token: float = 3.0) -> int:
    """
    估算单条消息的 token 数

    包含 content + thinking + tool_calls 的总和，
    外加每条消息约 4 token 的结构开销。
    """
    tokens = 4  # role / separator overhead

    tokens += estimate_content_tokens(message.content, chars_per_token)

    if message.thinking:
        tokens += max(1, int(len(message.thinking) / chars_per_token))

    if message.tool_calls:
        for tc in message.tool_calls:
            tokens += max(1, int(len(tc.name) / chars_per_token))
            args_str = str(tc.arguments) if tc.arguments else ""
            tokens += max(1, int(len(args_str) / chars_per_token))

    return tokens


def estimate_messages_tokens(
    messages: List[LLMMessage], chars_per_token: float = 3.0
) -> int:
    """估算消息列表的总 token 数"""
    return sum(estimate_message_tokens(m, chars_per_token) for m in messages)
