"""
LLM 配置定义

定义 LLM 客户端的配置类，支持不同的 provider 和认证方式。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


ProviderType = Literal["openai", "claude", "gemini", "kimi"]


@dataclass
class LLMConfig:
    """LLM 配置"""
    
    # 必填参数
    provider: ProviderType  # "openai" | "claude" | "gemini" | "kimi"
    api_key: str
    model: str  # e.g., "gpt-4o", "claude-3-5-sonnet-20241022", "gemini-1.5-pro"
    
    # 可选参数
    base_url: Optional[str] = None  # 自定义 API 端点 (用于代理或私有部署)
    timeout: int = 120  # 请求超时时间 (秒)
    max_retries: int = 2  # 最大重试次数
    
    # 额外的 headers (用于特殊场景)
    extra_headers: Dict[str, str] = field(default_factory=dict)
    
    # 备选端点池（用于多端点负载均衡 / 限流降级）
    # 每项: {"api_key": str, "base_url": str, "model": str}
    alt_endpoints: List[Dict[str, str]] = field(default_factory=list)
    
    def get_base_url(self) -> str:
        """获取 API 基础 URL"""
        if self.base_url:
            return self.base_url.rstrip("/")
        
        default_urls = {
            "openai": "https://api.openai.com/v1",
            "claude": "https://api.anthropic.com",
            "gemini": "https://generativelanguage.googleapis.com",
            "kimi": "https://api.moonshot.cn/v1",
        }
        return default_urls[self.provider]


# 预定义的模型配置
OPENAI_MODELS = [
    "gpt-5.2-pro",
    "gpt-5.2",
]

CLAUDE_MODELS = [
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250929",
]

GEMINI_MODELS = [
    "gemini-3-pro-preview",
    "gemini-3-flash-preview"
]

KIMI_MODELS = [
    "kimi-k2.5",
    "kimi-k2-0905-Preview",
    "kimi-k2-turbo-preview",
    "kimi-k2-thinking",
    "kimi-k2-thinking-turbo",
]

