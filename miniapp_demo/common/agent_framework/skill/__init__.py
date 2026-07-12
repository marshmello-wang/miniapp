"""
Skill 模块 - 为 Agent 提供 Skill 加载/卸载能力

支持两种加载模式:
- Static: 常驻在 system prompt 中，随 Agent 初始化加载
- Dynamic: 通过 load_skill 工具动态加载，经过 N 轮后自动卸载
"""

from .protocol import (
    SkillLoadType,
    SkillHookConfig,
    SkillDefinition,
    SkillState,
    SkillContent,
    SkillLoadResult,
)
from .registry import SkillRegistry
from .loader import SkillLoader
from .hooks import (
    HookDecision,
    SkillLoadHook,
    PermissionCheckHook,
    BUILTIN_HOOKS,
    run_hooks,
)
from .manager import SkillManager


def __getattr__(name):
    """延迟导入 LoadSkillTool 以避免与 builtin_tools 的循环引用"""
    if name == "LoadSkillTool":
        from common.agent_framework.builtin_tools.load_skill_tool import LoadSkillTool
        return LoadSkillTool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Protocol
    "SkillLoadType",
    "SkillHookConfig",
    "SkillDefinition",
    "SkillState",
    "SkillContent",
    "SkillLoadResult",
    # Registry
    "SkillRegistry",
    # Loader
    "SkillLoader",
    # Hooks
    "HookDecision",
    "SkillLoadHook",
    "PermissionCheckHook",
    "BUILTIN_HOOKS",
    "run_hooks",
    # Manager
    "SkillManager",
    # Tool
    "LoadSkillTool",
]
