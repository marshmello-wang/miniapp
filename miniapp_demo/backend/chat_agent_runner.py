"""Chat Agent Runner — 通用助手,所有已安装小程序 skill 作为 dynamic skill。

与 agent_runner.py 的区别:
- SkillConfig: 所有 app 的 skill 注册为 dynamic(而非 static),触发 load_skill 工具
- System Prompt: 通用助手角色
- bash cwd = APPS_DIR(不绑定单个小程序)
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from common.llm import LLMClient, LLMConfig
from common.agent_framework.agent_loop.react_agent import ReactAgent
from common.agent_framework.agent_loop.config import ReactAgentConfig, SkillConfig
from common.agent_framework.tool_adapter.registry import ToolRegistry
from common.agent_framework.tool_adapter.decorators import tool
from common.agent_framework.context_strategy.default_strategy import DefaultContextStrategy
from common.agent_framework.user_interface.inputs import TaskInput, Message
from common.agent_framework.user_interface.events import Event
from common.agent_framework.builtin_tools import BashTool
from common.agent_framework.builtin_tools.bash_tool import BashResult

from .app_registry import AppManifest, list_apps
from .agent_runner import _CwdBashExecutor, _build_memory_config, _make_app_emit_tool
from . import config as cfg


CHAT_SYSTEM_PROMPT = """\
你是一个友好的对话助手，通过自然对话帮助用户解决各种问题。

## 核心原则

1. **对话优先**：你的主要交互方式是对话，不是文件操作。用自然语言与用户交流。
2. **简洁有效**：回复简洁、有针对性，避免冗长的解释。
3. **主动匹配技能**：当用户的需求与已安装的小程序技能匹配时，使用 load_skill 加载对应技能，然后按技能指引完成任务。
4. **使用用户的语言**：始终用用户使用的语言回复。

## 可用工具

- **load_skill**：加载小程序技能（当用户需求匹配某个技能时使用）
- **bash**：执行命令（仅在技能要求时使用，如运行脚本）
- **app_emit**：向小程序界面推送结构化内容（仅在技能指引下使用）

## 工作方式

- 大多数情况下，直接用文字回答用户的问题
- 当用户的需求明确匹配某个小程序技能时，先用 load_skill 加载技能，再按技能指引执行
- 加载技能后，严格按照技能中的人设和流程行事
"""


def _build_skills_config() -> Dict[str, Any]:
    """构建所有已安装小程序的 dynamic skill 配置。"""
    manifests = list_apps()
    skills_config: Dict[str, Any] = {}
    for m in manifests:
        skills_config[m.id] = {
            "description": m.description or m.name,
            "content_file_path": f"{m.id}/{m.skill.content_file_path}",
            "load_type": "dynamic",
        }
    return skills_config


def get_chat_system_prompt() -> str:
    """返回 chat agent 使用的完整 system prompt（含 dynamic skill 候选列表）。"""
    sp = CHAT_SYSTEM_PROMPT
    skills_config = _build_skills_config()
    if skills_config:
        lines = ["\n## 可用技能（用 load_skill 激活）\n"]
        for name, conf in skills_config.items():
            lines.append(f"- **{name}**：{conf['description']}")
        sp += "\n".join(lines) + "\n"
    return sp


def create_chat_agent(store_dir_str: str = "") -> ReactAgent:
    """构建通用 Chat agent,所有已安装小程序 skill 作为 dynamic。"""
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
    tool_registry.register(BashTool(executor=bash_executor))
    tool_registry.register(_make_app_emit_tool())

    memory_config = _build_memory_config(memory_cfg_dict)

    skills_config = _build_skills_config()
    skill_config = SkillConfig(
        skills_config=skills_config,
        base_path=workspace_path,
    ) if skills_config else None

    return ReactAgent(ReactAgentConfig(
        llm_client=llm_client,
        tool_registry=tool_registry,
        context_strategy=DefaultContextStrategy(),
        system_prompt=get_chat_system_prompt(),
        max_iterations=agent_cfg.get("max_iterations", 30),
        max_tokens=agent_cfg.get("max_tokens", 8192),
        temperature=agent_cfg.get("temperature", 0.7),
        thinking_level=agent_cfg.get("thinking_level"),
        memory_config=memory_config,
        skill_config=skill_config,
    ))


def run_chat_agent(
    session_id: str,
    task_id: str,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    store_dir: str = "",
) -> Iterator[Event]:
    """执行 chat 一轮对话。"""
    agent = create_chat_agent(store_dir_str=store_dir)

    messages: List[Message] = []
    for msg in history or []:
        messages.append(Message.from_role_and_text(msg["role"], msg["content"]))
    messages.append(Message.from_role_and_text("user", user_message))

    task_input = TaskInput(session_id=session_id, task_id=task_id, messages=messages)
    for event in agent.run(task_input):
        yield event
