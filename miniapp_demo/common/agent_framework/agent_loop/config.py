"""
ReactAgent 配置定义 - 定义 React Agent 的配置参数
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, TYPE_CHECKING
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from common.agent_framework.tool_adapter.registry import ToolRegistry
from common.agent_framework.context_strategy.protocol import ContextStrategy
from common.agent_framework.context_strategy.truncation import TruncationStrategy
from common.agent_framework.context_strategy.memory.config import MemoryConfig
from common.llm import LLMClient

if TYPE_CHECKING:
    from .hooks import Hook


@dataclass
class SkillConfig:
    """
    Skill 配置

    Attributes:
        skills_config: Skill 定义配置字典（YAML 格式）
        base_path: skill 文件路径的基准目录
        global_envs: 全局环境变量
    """
    skills_config: Dict[str, Any] = field(default_factory=dict)
    base_path: str = ""
    global_envs: Dict[str, str] = field(default_factory=dict)


@dataclass
class SubAgentConfig:
    """
    子 Agent 配置

    Attributes:
        agents: 子 Agent 定义字典，key 为 agent name
    """
    agents: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReactAgentConfig:
    """
    ReactAgent 配置
    
    Attributes:
        llm_client: LLM 客户端实例（来自 common.llm）
        tool_registry: 工具注册中心
        context_strategy: 上下文构建策略
        system_prompt: 基础 system prompt
        max_iterations: 最大迭代次数（防止死循环），默认 20
        max_tokens: 模型调用的最大 token 数，默认 4096
        temperature: 模型温度参数，默认 1.0
        truncation_strategy: 截断策略（可选）
        hooks: 干预钩子列表（可选）
        sub_agent_config: 子 Agent 配置（可选）
    
    Example:
        >>> from common.llm import LLMClient, LLMConfig
        >>> config = ReactAgentConfig(
        ...     llm_client=LLMClient(LLMConfig(provider="openai", api_key="...", model="gpt-4o")),
        ...     tool_registry=registry,
        ...     context_strategy=DefaultStrategy(),
        ...     system_prompt="You are a helpful assistant."
        ... )
        >>> agent = create_react_agent(config)
    """
    llm_client: LLMClient
    tool_registry: ToolRegistry
    context_strategy: ContextStrategy
    system_prompt: str
    max_iterations: int = 20
    max_tokens: int = 4096
    temperature: float = 1.0
    thinking_level: Optional[str] = None  # None = 模型默认; "disabled" / "low" / "medium" / "high"
    truncation_strategy: Optional[TruncationStrategy] = None  # legacy，优先使用 memory_config
    memory_config: Optional[MemoryConfig] = None
    hooks: List["Hook"] = field(default_factory=list)
    end_tools: List[str] = field(default_factory=list)
    skill_config: Optional[SkillConfig] = None
    sub_agent_config: Optional[SubAgentConfig] = None
    system_prompt_vars: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """验证配置参数"""
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        if not self.system_prompt:
            raise ValueError("system_prompt cannot be empty")

