"""
load_skill 工具实现 - 供模型动态加载 Skill
"""
from typing import Dict, Any, Optional

from common.agent_framework.tool_adapter.protocol import Tool, ToolSchema, ToolResult
from common.agent_framework.tool_adapter.context import ToolContext
from common.agent_framework.skill.manager import SkillManager


class LoadSkillTool:
    """
    load_skill 工具

    当模型需要使用某个尚未加载的 skill 时调用。
    加载指定 skill 并返回其 instructions，同时通过 metadata 返回 binding_tools schemas。
    """

    def __init__(self, skill_manager: SkillManager):
        self._skill_manager = skill_manager
        self._current_round: int = 0

    @property
    def name(self) -> str:
        return "load_skill"

    @property
    def description(self) -> str:
        return (
            "当需要使用某个尚未加载的 skill 时调用。"
            "工具会加载指定 skill，并返回其 instructions，同时激活该 skill 关联的工具。"
        )

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            schema={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "要加载的 skill_name",
                    }
                },
                "required": ["skill_name"],
            },
        )

    def set_current_round(self, round_number: int) -> None:
        """设置当前轮次（由 ReactAgent 在每轮开始时调用）"""
        self._current_round = round_number

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        """
        执行 load_skill

        Returns:
            ToolResult:
                - formatted_data: <skill_content> 格式的指令文本
                - metadata["binding_tools"]: binding tool schemas (list of dict)
        """
        skill_name = parameters.get("skill_name", "")
        if not skill_name:
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error="skill_name is required",
                parameters=parameters,
            )

        # 从 context 中获取额外的环境变量
        envs: Dict[str, str] = {}
        if context:
            env_data = context.get("envs")
            if isinstance(env_data, dict):
                envs = env_data

        result = self._skill_manager.handle_load_skill(
            skill_name=skill_name,
            envs=envs,
            current_round=self._current_round,
        )

        if not result.success:
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error=result.error,
                metadata={"error_code": result.error_code},
                parameters=parameters,
            )

        content = result.content
        formatted = content.format_for_model()

        # 将 binding tool schemas 序列化到 metadata
        binding_tools_data = [
            schema.to_json_schema() for schema in content.binding_tool_schemas
        ]

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=formatted,
            formatted_data=formatted,
            metadata={
                "skill_name": skill_name,
                "binding_tools": binding_tools_data,
                "binding_tool_schemas": content.binding_tool_schemas,
            },
            parameters=parameters,
        )
