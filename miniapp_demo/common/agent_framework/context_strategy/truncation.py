"""
截断策略 - 定义上下文截断的协议和内置实现
"""
from typing import Protocol, List, Optional
from dataclasses import dataclass
import sys
import os

# 添加父目录到路径以支持相对导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 使用 common.llm 的 Message
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.llm import Message as LLMMessage


# ============================================================================
# 截断策略协议
# ============================================================================

class TruncationStrategy(Protocol):
    """
    截断策略协议
    
    用于控制上下文长度，避免超出模型 token 限制。
    不同的截断策略可以根据需求组合使用。
    
    Example:
        >>> truncation = SlidingWindowTruncation(max_turns=10)
        >>> truncated_messages = truncation.truncate(messages)
    """
    
    def truncate(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """
        截断消息列表
        
        Args:
            messages: 原始消息列表
        
        Returns:
            截断后的消息列表
        
        Note:
            - 实现时应保持消息的相对顺序
            - 不应修改原始消息列表
            - 第一条 user 消息通常应保留（作为任务描述）
        """
        ...


# ============================================================================
# 内置截断策略实现
# ============================================================================

@dataclass
class NoTruncation:
    """
    不截断策略（默认）
    
    直接返回原始消息列表，不做任何处理。
    适用于短对话或测试场景。
    """
    
    def truncate(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """直接返回原始消息列表"""
        return messages.copy()


@dataclass
class SlidingWindowTruncation:
    """
    滑动窗口截断策略
    
    保留最近 N 轮对话（一轮 = user + assistant）。
    可选保留第一条消息（通常是任务描述）。
    
    Attributes:
        max_turns: 最大保留轮数
        keep_first: 是否保留第一条消息
    
    Example:
        >>> truncation = SlidingWindowTruncation(max_turns=5, keep_first=True)
        >>> # 保留第一条消息 + 最近 5 轮对话
    """
    max_turns: int
    keep_first: bool = True
    
    def __post_init__(self):
        if self.max_turns < 1:
            raise ValueError("max_turns must be at least 1")
    
    def truncate(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """
        按滑动窗口截断消息
        
        Args:
            messages: 原始消息列表
        
        Returns:
            截断后的消息列表
        """
        if not messages:
            return []
        
        # 分离第一条消息和其余消息
        first_message = messages[0] if self.keep_first else None
        remaining = messages[1:] if self.keep_first else messages
        
        # 计算轮数并截断
        # 找出最近的 max_turns 轮对话
        turns = []
        current_turn: List[LLMMessage] = []
        
        for msg in remaining:
            current_turn.append(msg)
            # 当遇到 assistant 消息或 tool 消息后接 user 消息时，认为一轮结束
            if msg.role == "assistant":
                turns.append(current_turn)
                current_turn = []
        
        # 处理未完成的轮次
        if current_turn:
            turns.append(current_turn)
        
        # 保留最近的 max_turns 轮
        recent_turns = turns[-self.max_turns:] if len(turns) > self.max_turns else turns
        
        # 重新组合消息
        result: List[LLMMessage] = []
        if first_message:
            result.append(first_message)
        
        for turn in recent_turns:
            result.extend(turn)
        
        return result


@dataclass
class MessageCountTruncation:
    """
    消息数量截断策略
    
    简单地保留最近 N 条消息。
    可选保留第一条消息。
    
    Attributes:
        max_messages: 最大保留消息数
        keep_first: 是否保留第一条消息（不计入 max_messages）
    
    Example:
        >>> truncation = MessageCountTruncation(max_messages=20, keep_first=True)
    """
    max_messages: int
    keep_first: bool = True
    
    def __post_init__(self):
        if self.max_messages < 1:
            raise ValueError("max_messages must be at least 1")
    
    def truncate(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """
        按消息数量截断
        
        Args:
            messages: 原始消息列表
        
        Returns:
            截断后的消息列表
        """
        if not messages:
            return []
        
        if self.keep_first:
            first_message = messages[0]
            remaining = messages[1:]
            
            # 保留第一条 + 最近的 max_messages 条
            truncated = remaining[-self.max_messages:] if len(remaining) > self.max_messages else remaining
            return [first_message] + truncated
        else:
            # 直接保留最近的 max_messages 条
            return messages[-self.max_messages:] if len(messages) > self.max_messages else messages.copy()


@dataclass
class TokenEstimateTruncation:
    """
    Token 估算截断策略
    
    基于简单的字符数估算 token 数量，截断超出限制的消息。
    使用粗略估算（中文约 2 字符/token，英文约 4 字符/token）。
    
    Attributes:
        max_tokens: 最大 token 数估算值
        chars_per_token: 每个 token 的平均字符数（默认 3，中英文混合）
        keep_first: 是否保留第一条消息
    
    Note:
        这是一个粗略估算，实际 token 数可能有偏差。
        如需精确计算，请使用 tiktoken 等专业库。
    
    Example:
        >>> truncation = TokenEstimateTruncation(max_tokens=4000)
    """
    max_tokens: int
    chars_per_token: float = 3.0
    keep_first: bool = True
    
    def __post_init__(self):
        if self.max_tokens < 100:
            raise ValueError("max_tokens should be at least 100")
        if self.chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")
    
    def _estimate_tokens(self, message: LLMMessage) -> int:
        """估算单条消息的 token 数"""
        total_chars = 0
        content = message.content
        
        # LLMMessage.content 可以是字符串或列表
        if isinstance(content, str):
            total_chars = len(content)
        elif isinstance(content, list):
            for part in content:
                if hasattr(part, 'text'):
                    total_chars += len(part.text)
                # 图片内容暂时按固定 token 估算
                elif hasattr(part, 'data'):
                    total_chars += 500 * self.chars_per_token  # 图片约 500 tokens
        
        return int(total_chars / self.chars_per_token)
    
    def truncate(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """
        按 token 估算截断
        
        从后往前保留消息，直到达到 token 限制。
        
        Args:
            messages: 原始消息列表
        
        Returns:
            截断后的消息列表
        """
        if not messages:
            return []
        
        first_message = messages[0] if self.keep_first else None
        remaining = messages[1:] if self.keep_first else messages
        
        # 计算第一条消息的 token 数
        first_tokens = self._estimate_tokens(first_message) if first_message else 0
        available_tokens = self.max_tokens - first_tokens
        
        # 从后往前累积消息
        result_reversed: List[LLMMessage] = []
        current_tokens = 0
        
        for msg in reversed(remaining):
            msg_tokens = self._estimate_tokens(msg)
            if current_tokens + msg_tokens <= available_tokens:
                result_reversed.append(msg)
                current_tokens += msg_tokens
            else:
                break
        
        # 反转并添加第一条消息
        result = list(reversed(result_reversed))
        if first_message:
            result.insert(0, first_message)
        
        return result


@dataclass 
class CompositeTruncation:
    """
    组合截断策略
    
    按顺序应用多个截断策略。
    
    Attributes:
        strategies: 截断策略列表，按顺序执行
    
    Example:
        >>> truncation = CompositeTruncation([
        ...     TokenEstimateTruncation(max_tokens=8000),
        ...     SlidingWindowTruncation(max_turns=20)
        ... ])
    """
    strategies: List[TruncationStrategy]
    
    def truncate(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """
        按顺序应用所有截断策略
        
        Args:
            messages: 原始消息列表
        
        Returns:
            截断后的消息列表
        """
        result = messages
        for strategy in self.strategies:
            result = strategy.truncate(result)
        return result

