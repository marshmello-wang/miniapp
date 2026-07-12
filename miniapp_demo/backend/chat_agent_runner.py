"""Chat Agent Runner — 通用助手,用 show_miniapp_entry 展示小程序入口。

与 agent_runner.py 的区别:
- 不使用 dynamic skills / load_skill,改用 show_miniapp_entry 工具展示入口卡片
- System Prompt: 通用助手角色
- bash cwd = APPS_DIR（不绑定单个小程序）
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from common.llm import LLMClient, LLMConfig
from common.agent_framework.agent_loop.react_agent import ReactAgent
from common.agent_framework.agent_loop.config import ReactAgentConfig
from common.agent_framework.tool_adapter.registry import ToolRegistry
from common.agent_framework.tool_adapter.decorators import tool
from common.agent_framework.context_strategy.default_strategy import DefaultContextStrategy
from common.agent_framework.user_interface.inputs import TaskInput, Message
from common.agent_framework.user_interface.events import Event
from common.agent_framework.builtin_tools import BashTool

from .app_registry import list_apps, get_app
from .agent_runner import _CwdBashExecutor, _build_memory_config, _make_app_emit_tool
from . import config as cfg


CHAT_SYSTEM_PROMPT = """\
你是一个友好的对话助手，通过自然对话帮助用户解决各种问题。

## 核心原则

1. **对话优先**：你的主要交互方式是对话，不是文件操作。用自然语言与用户交流。
2. **简洁有效**：回复简洁、有针对性，避免冗长的解释。
3. **主动匹配小程序**：当用户的需求与某个小程序匹配时，使用 show_miniapp_entry 展示入口，让用户点击进入。
4. **使用用户的语言**：始终用用户使用的语言回复。

## 工作方式

- 大多数情况下，直接用文字回答用户的问题
- 当用户的需求明确匹配某个小程序时，调用 show_miniapp_entry 展示入口卡片，并用简短文字引导用户点击进入
- 不要自己扮演小程序的角色，小程序有独立的交互体验
"""


def _make_show_miniapp_entry_tool():
    """创建 show_miniapp_entry 工具，供 chat agent 展示小程序入口卡片。"""

    @tool(
        name="show_miniapp_entry",
        description="向用户展示一个小程序入口卡片。当用户需求匹配某个小程序时调用。",
    )
    def show_miniapp_entry(app_id: str, context=None) -> dict:
        manifest = get_app(app_id)
        if manifest is None:
            return {"success": False, "error": f"小程序 '{app_id}' 不存在"}
        return {
            "success": True,
            "message": f"已展示「{manifest.name}」小程序入口，用户可点击进入。",
        }

    return show_miniapp_entry


def get_chat_system_prompt() -> str:
    """返回 chat agent 使用的完整 system prompt（含可用小程序列表）。"""
    sp = CHAT_SYSTEM_PROMPT
    manifests = list_apps()
    if manifests:
        lines = ["\n## 可用小程序（用 show_miniapp_entry 展示入口）\n"]
        for m in manifests:
            lines.append(f"- **{m.id}**：{m.description or m.name}")
        sp += "\n".join(lines) + "\n"
    return sp


def create_chat_agent(store_dir_str: str = "") -> ReactAgent:
    """构建通用 Chat agent，用 show_miniapp_entry 展示小程序入口。"""
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
    tool_registry.register(_make_show_miniapp_entry_tool())

    memory_config = _build_memory_config(memory_cfg_dict)

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
