"""Chat Agent Runner — 通用助手,把所有小程序作为 dynamic skill 注册。

与 agent_runner.py 的区别:
- 不绑定单个小程序;把全部小程序注册为 dynamic skill,由 agent 用 load_skill 按需加载
- System Prompt: 通用助手角色
- bash cwd = APPS_DIR（不绑定单个小程序）
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from common.llm import LLMClient, LLMConfig
from common.agent_framework.agent_loop.react_agent import ReactAgent
from common.agent_framework.agent_loop.config import ReactAgentConfig, SkillConfig
from common.agent_framework.tool_adapter.registry import ToolRegistry
from common.agent_framework.user_interface.inputs import TaskInput, Message
from common.agent_framework.user_interface.events import Event

from .app_registry import list_apps
from .agent_runner import (
    MiniAppBashTool,
    _AgentSignalHook,
    _CwdBashExecutor,
    _build_memory_config,
    _make_app_emit_tool,
    _MiniappContextStrategy,
    _dicts_to_llm_messages,
)
from . import config as cfg


def _rich_history_to_llm_messages(history: Optional[List[Dict[str, Any]]] = None):
    """把 load_history_rich() 的标准 API 格式 dicts 转成 LLMMessage 列表。"""
    return _dicts_to_llm_messages(history or [])



class ChatContextStrategy(_MiniappContextStrategy):
    """在默认策略基础上预加载富历史（含 tool call/result）的上下文策略。"""

    def __init__(self, history_messages=None):
        super().__init__()
        if history_messages:
            self.set_rich_history(history_messages)


CHAT_SYSTEM_PROMPT = """\
你是一个友好的对话助手，通过自然对话帮助用户解决各种问题。

## 核心原则

1. **对话优先**：你的主要交互方式是对话，用自然语言与用户交流。
2. **简洁有效**：回复简洁、有针对性，避免冗长的解释。
3. **按需加载小程序能力**：当用户的需求与某个小程序匹配时，用 load_skill 加载对应小程序，然后按该 Skill 的说明使用它的能力与 UI 命令。
4. **使用用户的语言**：始终用用户使用的语言回复。

## 工作方式

- 大多数情况下，直接用文字回答用户的问题。
- 当用户的需求匹配某个小程序时，先 load_skill 加载它，再遵循该 Skill 的工作流完成任务。
- load_skill 本身不会打开右侧 UI；只有后续该 Skill 声明的 UI CLI（bash 脚本或 app_emit）才会影响右栏界面。

## 严格执行 Skill 指令（最重要）

加载 Skill 后，你必须**严格遵循**该 Skill 文档中的所有工作流、禁止条款和工具调用方式。具体要求：
- **按 Skill 规定的步骤顺序执行**，不要跳步、不要自行编造工具或命令。
- **Skill 说用什么工具就用什么工具**（如 show_question.py、app_emit），不要自己写 python 脚本替代。
- **Skill 说内容放 UI 就放 UI**，绝对不要把应该在 UI 展示的内容写在 Chat 正文里。
- **Skill 说先打开 UI 就必须先打开 UI**（通过 app_emit open 命令），不要跳过这一步直接在 Chat 里完成任务。
- 如果 Skill 有"绝对禁止"部分，其中的每一条都是硬约束，违反即失败。
"""


def _skills_config_from_apps() -> Dict[str, Any]:
    """把所有已注册小程序转成 dynamic skill 配置，供 agent 用 load_skill 按需加载。"""
    skills_config: Dict[str, Any] = {}
    for manifest in list_apps():
        skills_config[manifest.id] = {
            "description": manifest.description or manifest.name,
            "content_file_path": f"{manifest.id}/{manifest.skill.content_file_path}",
            "load_type": "dynamic",
            "binding_tools": manifest.skill.binding_tools,
        }
    return skills_config


def get_chat_system_prompt() -> str:
    """返回 chat agent 使用的完整 system prompt（含可用小程序列表）。"""
    sp = CHAT_SYSTEM_PROMPT
    manifests = list_apps()
    if manifests:
        lines = ["\n## 可用小程序（用 load_skill 加载后使用）\n"]
        for m in manifests:
            lines.append(f"- **{m.id}**：{m.description or m.name}")
        sp += "\n".join(lines) + "\n"
    return sp


def create_chat_agent(
    store_dir_str: str = "",
    rich_history: Optional[List[Dict[str, Any]]] = None,
) -> ReactAgent:
    """构建通用 Chat agent，把全部小程序注册为 dynamic skill。

    rich_history 为标准 LLM API 消息格式(含 tool call/result),通过
    ChatContextStrategy 注入上下文,使 agent 能记住历史轮次的工具调用。
    """
    config = cfg.load_config()
    llm_cfg = cfg.get_llm_config(config)
    agent_cfg = cfg.get_agent_config(config)
    memory_cfg_dict = cfg.get_memory_config(config)

    llm_client = LLMClient(LLMConfig(
        provider=llm_cfg["provider"],
        api_key=llm_cfg["api_key"],
        model=llm_cfg["model"],
        base_url=llm_cfg.get("base_url"),
    ))

    workspace_path = str(cfg.APPS_DIR)
    tool_registry = ToolRegistry()

    bash_executor = _CwdBashExecutor(cwd=workspace_path, store_dir=store_dir_str)
    tool_registry.register(MiniAppBashTool(executor=bash_executor))
    tool_registry.register(_make_app_emit_tool())

    memory_config = _build_memory_config(memory_cfg_dict)

    skill_config = SkillConfig(
        skills_config=_skills_config_from_apps(),
        base_path=str(cfg.APPS_DIR),
    )

    context_strategy = ChatContextStrategy(
        history_messages=_rich_history_to_llm_messages(rich_history or [])
    )

    return ReactAgent(ReactAgentConfig(
        llm_client=llm_client,
        tool_registry=tool_registry,
        context_strategy=context_strategy,
        system_prompt=get_chat_system_prompt(),
        max_iterations=agent_cfg.get("max_iterations", 30),
        max_tokens=agent_cfg.get("max_tokens", 8192),
        temperature=agent_cfg.get("temperature", 0.7),
        thinking_level=agent_cfg.get("thinking_level"),
        memory_config=memory_config,
        skill_config=skill_config,
        hooks=[_AgentSignalHook()],
    ))


def run_chat_agent(
    session_id: str,
    task_id: str,
    user_message: str,
    rich_history: Optional[List[Dict[str, Any]]] = None,
    store_dir: str = "",
) -> Iterator[Event]:
    """执行 chat 一轮对话。

    rich_history 为标准 LLM API 消息格式(含白名单内的 tool call/result),
    通过 context strategy 注入,当前用户消息单独放入 TaskInput。
    """
    agent = create_chat_agent(store_dir_str=store_dir, rich_history=rich_history)

    messages = [Message.from_role_and_text("user", user_message)]
    task_input = TaskInput(session_id=session_id, task_id=task_id, messages=messages)
    for event in agent.run(task_input):
        yield event
