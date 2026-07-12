"""
Skill 加载器 - 读取 skill.md 文件并解析 binding tools
"""
from typing import List, Optional
from pathlib import Path

from common.agent_framework.tool_adapter.protocol import ToolSchema
from common.agent_framework.tool_adapter.registry import ToolRegistry

from .protocol import SkillDefinition, SkillContent


class SkillLoader:
    """
    Skill 内容加载器

    负责从文件系统读取 skill.md，并从 ToolRegistry 中解析 binding tools 的 schemas。
    """

    def __init__(self, base_path: str = ""):
        """
        Args:
            base_path: skill 文件路径的基准目录。
                       content_file_path 如果是相对路径，则基于此目录解析。
        """
        self._base_path = Path(base_path) if base_path else Path(".")

    def load_content(
        self,
        skill_def: SkillDefinition,
        tool_registry: ToolRegistry
    ) -> SkillContent:
        """
        加载 Skill 内容

        Args:
            skill_def: Skill 定义
            tool_registry: 工具注册中心（用于解析 binding tools）

        Returns:
            SkillContent: 加载后的内容

        Raises:
            FileNotFoundError: skill.md 文件不存在时
        """
        instructions = self._read_skill_file(skill_def.content_file_path)
        binding_tool_schemas = self._resolve_binding_tools(
            skill_def.binding_tools, tool_registry
        )

        return SkillContent(
            skill_name=skill_def.name,
            instructions=instructions,
            binding_tool_schemas=binding_tool_schemas,
        )

    def _read_skill_file(self, content_file_path: str) -> str:
        """读取 skill.md 文件内容"""
        path = Path(content_file_path)
        if not path.is_absolute():
            path = self._base_path / path

        if not path.exists():
            raise FileNotFoundError(f"Skill file not found: {path}")

        return path.read_text(encoding="utf-8")

    def _resolve_binding_tools(
        self,
        tool_names: List[str],
        tool_registry: ToolRegistry
    ) -> List[ToolSchema]:
        """
        从 ToolRegistry 中解析 binding tools 对应的 ToolSchema。
        不存在的 tool 会被跳过（不报错）。
        """
        schemas: List[ToolSchema] = []
        for name in tool_names:
            tool = tool_registry.get(name)
            if tool is not None:
                schemas.append(tool.schema)
        return schemas
