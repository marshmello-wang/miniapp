"""
Skill 生命周期管理器 - 编排 static/dynamic skill 的加载与卸载
"""
from typing import Dict, List, Optional

from common.agent_framework.tool_adapter.protocol import ToolSchema
from common.agent_framework.tool_adapter.registry import ToolRegistry

from .protocol import (
    SkillDefinition,
    SkillState,
    SkillContent,
    SkillLoadResult,
    SkillLoadType,
)
from .registry import SkillRegistry
from .loader import SkillLoader
from .hooks import run_hooks, HookDecision


class SkillManager:
    """
    Skill 生命周期管理器

    负责:
    - 初始化阶段: 加载 static skills，生成 dynamic skill 候选描述
    - 运行阶段: 处理 load_skill 请求，管理 binding tools
    - 卸载阶段: 基于轮次计数自动 offload dynamic skills
    """

    def __init__(
        self,
        skill_registry: SkillRegistry,
        tool_registry: ToolRegistry,
        skill_loader: SkillLoader,
        global_envs: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            skill_registry: Skill 定义注册中心
            tool_registry: 工具注册中心（用于解析 binding tools）
            skill_loader: Skill 文件加载器
            global_envs: 全局环境变量
        """
        self._skill_registry = skill_registry
        self._tool_registry = tool_registry
        self._skill_loader = skill_loader
        self._global_envs = global_envs or {}

        # 运行时状态: skill_name -> SkillState
        self._states: Dict[str, SkillState] = {}

        # 已加载的 skill 内容缓存: skill_name -> SkillContent
        self._loaded_contents: Dict[str, SkillContent] = {}

    # ========================================================================
    # 初始化阶段
    # ========================================================================

    def get_static_skill_prompt(self) -> str:
        """
        生成 static skills 的 system prompt 片段。

        Static skills 的 skill.md 内容直接拼入 system prompt。
        """
        static_skills = self._skill_registry.list_static()
        if not static_skills:
            return ""

        parts = ["## Static Skills\n"]
        for skill_def in static_skills:
            try:
                content = self._skill_loader.load_content(skill_def, self._tool_registry)
                self._loaded_contents[skill_def.name] = content
                self._states[skill_def.name] = SkillState(
                    skill_name=skill_def.name,
                    is_loaded=True,
                    loaded_at_round=0,
                    keep_task_round=999999,  # static 永不卸载
                )
                parts.append(content.format_for_model())
            except FileNotFoundError:
                parts.append(
                    f'<skill_content name="{skill_def.name}">\n'
                    f"[Error: skill file not found: {skill_def.content_file_path}]\n"
                    f"</skill_content>"
                )

        return "\n\n".join(parts)

    def get_static_skill_binding_tools(self) -> Dict[str, List[ToolSchema]]:
        """
        获取所有 static skills 的 binding tool schemas（按 skill_name 分组）。
        """
        result: Dict[str, List[ToolSchema]] = {}
        for skill_def in self._skill_registry.list_static():
            content = self._loaded_contents.get(skill_def.name)
            if content and content.binding_tool_schemas:
                result[skill_def.name] = content.binding_tool_schemas
        return result

    def get_dynamic_skill_candidates_prompt(self) -> str:
        """
        生成 dynamic skill 候选列表的描述文本（放在 system prompt 中引导模型调用 load_skill）。
        """
        dynamic_skills = self._skill_registry.list_dynamic()
        if not dynamic_skills:
            return ""

        lines = [
            "## Dynamic Skills\n",
            "以下 skill 需要通过 load_skill 工具加载，获得 skill 的详细内容和工具:\n",
        ]
        for skill_def in dynamic_skills:
            lines.append(f"- **{skill_def.name}**: {skill_def.description}")

        return "\n".join(lines)

    # ========================================================================
    # 加载阶段
    # ========================================================================

    def handle_load_skill(
        self,
        skill_name: str,
        envs: Optional[Dict[str, str]] = None,
        current_round: int = 0,
    ) -> SkillLoadResult:
        """
        处理 load_skill 请求

        Args:
            skill_name: 要加载的 skill 名称
            envs: 请求携带的环境变量（与全局 envs 合并）
            current_round: 当前轮次

        Returns:
            SkillLoadResult
        """
        skill_def = self._skill_registry.get(skill_name)
        if skill_def is None:
            return SkillLoadResult(
                success=False,
                error=f"Skill '{skill_name}' not found",
                error_code="not_found",
            )

        # 已加载的幂等返回
        state = self._states.get(skill_name)
        if state and state.is_loaded:
            content = self._loaded_contents.get(skill_name)
            if content:
                return SkillLoadResult(success=True, content=content)

        # 合并环境变量
        merged_envs = {**self._global_envs, **skill_def.env_config}
        if envs:
            merged_envs.update(envs)

        # 执行 load hooks
        if skill_def.load_hooks:
            decision = run_hooks(skill_def.load_hooks, merged_envs)
            if decision.type == "deny":
                return SkillLoadResult(
                    success=False,
                    error=f"Permission denied: {decision.deny_reason}",
                    error_code="permission_denied",
                )
            if decision.type == "ask":
                missing = ", ".join(decision.ask_permissions)
                return SkillLoadResult(
                    success=False,
                    error=f"Missing permissions: {missing}",
                    error_code="permission_denied",
                )

        # 加载内容
        try:
            content = self._skill_loader.load_content(skill_def, self._tool_registry)
        except FileNotFoundError as e:
            return SkillLoadResult(
                success=False,
                error=str(e),
                error_code="file_not_found",
            )

        # 更新状态
        self._loaded_contents[skill_name] = content
        self._states[skill_name] = SkillState(
            skill_name=skill_name,
            is_loaded=True,
            loaded_at_round=current_round,
            keep_task_round=skill_def.keep_task_round,
        )

        return SkillLoadResult(success=True, content=content)

    # ========================================================================
    # 卸载阶段
    # ========================================================================

    def check_offload(self, current_round: int) -> List[str]:
        """
        检查需要卸载的 dynamic skills

        Args:
            current_round: 当前轮次

        Returns:
            需要卸载的 skill name 列表
        """
        to_offload: List[str] = []
        for name, state in self._states.items():
            skill_def = self._skill_registry.get(name)
            if skill_def and skill_def.load_type == SkillLoadType.DYNAMIC:
                if state.should_offload(current_round):
                    to_offload.append(name)
        return to_offload

    def execute_offload(self, skill_names: List[str]) -> None:
        """
        执行卸载操作（更新内部状态）

        Args:
            skill_names: 要卸载的 skill 名称列表
        """
        for name in skill_names:
            state = self._states.get(name)
            if state:
                state.mark_unloaded()
            self._loaded_contents.pop(name, None)

    def get_offload_message(self, skill_names: List[str]) -> str:
        """生成卸载引导文案"""
        if not skill_names:
            return ""
        names_str = "\n".join(f"- {name}" for name in skill_names)
        return (
            f"以下 skills 已经被卸载:\n{names_str}\n"
            f"如果想继续使用该 skill，请使用 load_skill 工具重新加载。"
        )

    # ========================================================================
    # 查询方法
    # ========================================================================

    def get_active_binding_tools(self) -> Dict[str, List[ToolSchema]]:
        """
        获取当前所有已加载 skill 的 binding tool schemas（按 skill_name 分组）。
        """
        result: Dict[str, List[ToolSchema]] = {}
        for name, state in self._states.items():
            if state.is_loaded:
                content = self._loaded_contents.get(name)
                if content and content.binding_tool_schemas:
                    result[name] = content.binding_tool_schemas
        return result

    def get_skill_binding_tools(self, skill_name: str) -> List[ToolSchema]:
        """获取指定 skill 的 binding tool schemas"""
        content = self._loaded_contents.get(skill_name)
        if content:
            return content.binding_tool_schemas
        return []

    def is_loaded(self, skill_name: str) -> bool:
        """检查指定 skill 是否已加载"""
        state = self._states.get(skill_name)
        return state.is_loaded if state else False
