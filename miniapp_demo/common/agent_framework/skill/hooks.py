"""
Skill 加载前 Hooks - 权限检查等前置钩子
"""
from dataclasses import dataclass, field
from typing import Protocol, Dict, List, Any, Literal


@dataclass
class HookDecision:
    """
    Hook 决策结果

    Attributes:
        type: 决策类型
            - "allow": 允许加载
            - "deny": 拒绝加载
            - "ask": 需要用户补充权限
        ask_permissions: type=ask 时，缺失的权限列表
        deny_reason: type=deny 时，拒绝原因
    """
    type: Literal["allow", "deny", "ask"]
    ask_permissions: List[str] = field(default_factory=list)
    deny_reason: str = ""

    @classmethod
    def allow(cls) -> "HookDecision":
        return cls(type="allow")

    @classmethod
    def deny(cls, reason: str) -> "HookDecision":
        return cls(type="deny", deny_reason=reason)

    @classmethod
    def ask(cls, permissions: List[str]) -> "HookDecision":
        return cls(type="ask", ask_permissions=permissions)


class SkillLoadHook(Protocol):
    """Skill 加载前钩子协议"""

    def execute(self, envs: Dict[str, str], parameters: Dict[str, Any]) -> HookDecision:
        """
        执行 hook 检查

        Args:
            envs: 当前环境变量
            parameters: hook 配置中的参数

        Returns:
            HookDecision: 决策结果
        """
        ...


class PermissionCheckHook:
    """
    内置权限检查 Hook

    检查 parameters["permissions"] 中列出的 env key 是否在 envs 中存在且非空。
    """

    def execute(self, envs: Dict[str, str], parameters: Dict[str, Any]) -> HookDecision:
        permissions = parameters.get("permissions", [])
        missing = []

        for perm in permissions:
            key = perm
            if perm.startswith("env/"):
                key = perm[4:]

            value = envs.get(key, "")
            if not value:
                missing.append(perm)

        if not missing:
            return HookDecision.allow()

        return HookDecision.ask(missing)


# Hook 注册表：hook_name -> Hook 类
BUILTIN_HOOKS: Dict[str, type] = {
    "permission_check": PermissionCheckHook,
}


def run_hooks(
    hook_configs: List[Any],
    envs: Dict[str, str]
) -> HookDecision:
    """
    按顺序执行 hook 链，第一个非 allow 的结果即中断返回。

    Args:
        hook_configs: SkillHookConfig 列表
        envs: 环境变量

    Returns:
        HookDecision: 最终决策（全部通过则返回 allow）
    """
    for hook_config in hook_configs:
        hook_cls = BUILTIN_HOOKS.get(hook_config.hook_name)
        if hook_cls is None:
            continue

        hook_instance = hook_cls()
        decision = hook_instance.execute(envs, hook_config.parameters)

        if decision.type != "allow":
            return decision

    return HookDecision.allow()
