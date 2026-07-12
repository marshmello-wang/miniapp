"""
Skill 注册中心 - 管理 Skill 定义的存储与检索
"""
from typing import Dict, List, Optional, Any

from .protocol import SkillDefinition, SkillLoadType, SkillHookConfig


class SkillRegistry:
    """
    Skill 注册中心

    管理所有已注册的 SkillDefinition，支持按类型筛选和从配置批量加载。
    """

    def __init__(self):
        self._skills: Dict[str, SkillDefinition] = {}

    def register(self, skill_def: SkillDefinition) -> None:
        """
        注册 Skill 定义

        Raises:
            ValueError: skill name 已存在时
        """
        if skill_def.name in self._skills:
            raise ValueError(f"Skill '{skill_def.name}' already registered")
        self._skills[skill_def.name] = skill_def

    def unregister(self, name: str) -> None:
        """注销 Skill 定义"""
        self._skills.pop(name, None)

    def get(self, name: str) -> Optional[SkillDefinition]:
        """获取 Skill 定义，不存在返回 None"""
        return self._skills.get(name)

    def list_all(self) -> List[SkillDefinition]:
        """列出所有已注册的 Skill"""
        return list(self._skills.values())

    def list_static(self) -> List[SkillDefinition]:
        """筛选 static 类型的 Skill"""
        return [s for s in self._skills.values() if s.load_type == SkillLoadType.STATIC]

    def list_dynamic(self) -> List[SkillDefinition]:
        """筛选 dynamic 类型的 Skill"""
        return [s for s in self._skills.values() if s.load_type == SkillLoadType.DYNAMIC]

    def has(self, name: str) -> bool:
        """检查 Skill 是否已注册"""
        return name in self._skills

    def clear(self) -> None:
        """清空所有注册"""
        self._skills.clear()

    def __len__(self) -> int:
        return len(self._skills)

    def load_from_config(self, config: Dict[str, Any]) -> None:
        """
        从配置字典批量加载 Skill 定义

        配置格式 (对应 YAML):
            skill_name:
                description: "..."
                content_file_path: "./skills/xxx/skill.md"
                load_type: "static" | "dynamic"
                keep_task_round: 3
                env_config:
                    key1: val1
                binding_tools:
                    - tool_name_1
                    - tool_name_2
                load_hooks:
                    - hook_name: permission_check
                      parameters:
                          permissions:
                              - "env/user_id"
        """
        for name, skill_conf in config.items():
            if not isinstance(skill_conf, dict):
                continue

            load_type_str = skill_conf.get("load_type", "dynamic")
            try:
                load_type = SkillLoadType(load_type_str)
            except ValueError:
                load_type = SkillLoadType.DYNAMIC

            hooks = []
            for hook_conf in skill_conf.get("load_hooks", []):
                if isinstance(hook_conf, dict) and "hook_name" in hook_conf:
                    hooks.append(SkillHookConfig(
                        hook_name=hook_conf["hook_name"],
                        parameters={k: v for k, v in hook_conf.items() if k != "hook_name"}
                    ))

            skill_def = SkillDefinition(
                name=name,
                description=skill_conf.get("description", ""),
                content_file_path=skill_conf.get("content_file_path", ""),
                load_type=load_type,
                keep_task_round=skill_conf.get("keep_task_round", 3),
                env_config=skill_conf.get("env_config", {}),
                binding_tools=skill_conf.get("binding_tools", []),
                load_hooks=hooks,
            )
            self.register(skill_def)
