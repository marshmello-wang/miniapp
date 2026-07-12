"""
Skill 协议定义 - 核心数据结构
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional, Literal

from common.agent_framework.tool_adapter.protocol import ToolSchema


class SkillLoadType(str, Enum):
    """Skill 加载类型"""
    STATIC = "static"
    DYNAMIC = "dynamic"


@dataclass
class SkillHookConfig:
    """
    Skill 加载 Hook 配置

    Attributes:
        hook_name: hook 类型标识 (如 "permission_check")
        parameters: hook 参数 (如 permissions 列表)
    """
    hook_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillDefinition:
    """
    Skill 完整定义

    Attributes:
        name: skill 唯一标识
        description: 简短描述（展示在 dynamic candidates 列表中）
        content_file_path: skill.md 文件路径
        load_type: 加载类型 (static / dynamic)
        keep_task_round: dynamic skill 保留的轮次数（超过后自动 offload）
        env_config: 环境变量配置
        binding_tools: 关联的 tool name 列表（引用 ToolRegistry 中已注册的 tool）
        load_hooks: 加载前执行的 hook 配置列表
    """
    name: str
    description: str
    content_file_path: str
    load_type: SkillLoadType = SkillLoadType.DYNAMIC
    keep_task_round: int = 3
    env_config: Dict[str, str] = field(default_factory=dict)
    binding_tools: List[str] = field(default_factory=list)
    load_hooks: List[SkillHookConfig] = field(default_factory=list)


@dataclass
class SkillState:
    """
    Skill 运行时状态

    Attributes:
        skill_name: 关联的 skill name
        is_loaded: 是否已加载
        loaded_at_round: 在第几轮加载的（用于计算 offload）
        keep_task_round: 保留轮数
    """
    skill_name: str
    is_loaded: bool = False
    loaded_at_round: int = -1
    keep_task_round: int = 3

    def should_offload(self, current_round: int) -> bool:
        """判断是否应该卸载"""
        if not self.is_loaded:
            return False
        if self.loaded_at_round < 0:
            return False
        return (current_round - self.loaded_at_round) >= self.keep_task_round

    def mark_loaded(self, round_number: int) -> None:
        """标记为已加载"""
        self.is_loaded = True
        self.loaded_at_round = round_number

    def mark_unloaded(self) -> None:
        """标记为已卸载"""
        self.is_loaded = False
        self.loaded_at_round = -1


@dataclass
class SkillContent:
    """
    加载后的 Skill 内容

    Attributes:
        skill_name: skill 名称
        instructions: skill.md 正文内容
        binding_tool_schemas: 关联的 tool schemas 列表
    """
    skill_name: str
    instructions: str
    binding_tool_schemas: List[ToolSchema] = field(default_factory=list)

    def format_for_model(self) -> str:
        """格式化为传给模型的 tool response 文本"""
        return f'<skill_content name="{self.skill_name}">\n{self.instructions}\n</skill_content>'


@dataclass
class SkillLoadResult:
    """
    load_skill 操作的返回结果

    Attributes:
        success: 是否成功
        content: 成功时的 SkillContent
        error: 失败时的错误信息
        error_code: 错误码 (如 "not_found", "permission_denied")
    """
    success: bool
    content: Optional[SkillContent] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
