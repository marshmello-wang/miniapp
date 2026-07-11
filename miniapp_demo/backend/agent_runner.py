"""Agent Runner —— 接入 LLM,构建方式与 lite_code 完全一致。

复用 lite_code 的:自定义工具(read_file/list_files/grep_search)、系统提示词
(get_system_prompt)、以及 create_agent 的全部装配(LLMClient + ToolRegistry +
MemoryConfig + DefaultContextStrategy + OrchestratorAgent 图 + run_task)。

小程序特有的增量(不改变 lite_code 的接入方式):
- bash 的 cwd = 小程序根目录,并注入 MINIAPP_STORE(业务 store 目录)。
- 额外注册 app_emit 工具(把 structuredContent 推到界面)。
- 按单个小程序 skill 构建 SkillConfig;mini-app 场景说明通过 get_system_prompt 的
  extra_context 注入(lite_code 原生支持的通道)。
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from common.llm import LLMClient, LLMConfig
from common.agent_framework.agent_loop.react_agent import ReactAgent
from common.agent_framework.agent_loop.config import ReactAgentConfig, SkillConfig
from common.agent_framework.tool_adapter.registry import ToolRegistry
from common.agent_framework.tool_adapter.decorators import tool
from common.agent_framework.context_strategy.default_strategy import DefaultContextStrategy
from common.agent_framework.context_strategy.memory.config import (
    MemoryConfig, L1Config, L2Config,
    AllocationBudgetConfig, HistoryCollapseConfig, CollapseStrategyConfig,
)
from common.agent_framework.user_interface.inputs import TaskInput, Message
from common.agent_framework.user_interface.events import Event
from common.agent_framework.builtin_tools import BashTool, TextEditTool
from common.agent_framework.builtin_tools.bash_tool import BashResult

# 直接复用 lite_code 的工具与系统提示词(与 lite_code 完全一样)
from lite_code.backend.tools import ReadFileTool, ListFilesTool, GrepSearchTool
from lite_code.backend.context.system_prompt import get_system_prompt

from .app_registry import AppManifest
from . import config as cfg


# mini-app 场景说明:通过 lite_code 原生的 extra_context 通道注入
MINIAPP_EXTRA_CONTEXT = (
    "This session powers a mini-app (小程序) running in a sandbox, not a generic coding task.\n"
    "- Business data lives in the directory given by the environment variable MINIAPP_STORE.\n"
    "- The app ships scripts under `scripts/`; run them with bash to query or mutate business data.\n"
    "- To change what the user sees on screen, call the `app_emit` tool with a `structuredContent` JSON object.\n"
    "- Follow the app's SKILL for the exact structuredContent schema and the intended workflow."
)


class _CwdBashExecutor:
    """LocalBashExecutor with working directory support(仿 lite_code),额外注入 MINIAPP_STORE。"""

    def __init__(self, cwd: str = ".", store_dir: str = ""):
        self._cwd = cwd
        self._store_dir = store_dir

    async def execute(self, command: str, timeout: float) -> BashResult:
        env = dict(os.environ)
        if self._store_dir:
            env["MINIAPP_STORE"] = self._store_dir
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise

        return BashResult(
            exit_code=process.returncode or 0,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
        )


def _build_memory_config(memory_dict: Dict[str, Any]) -> Optional[MemoryConfig]:
    """从 config dict 构建 MemoryConfig(与 lite_code 完全一致)。"""
    l1_dict = memory_dict.get("l1")
    if not l1_dict:
        return None

    budget_dict = l1_dict.get("budget", {})
    budget = AllocationBudgetConfig(
        max_total_tokens=budget_dict.get("max_total_tokens", 128000),
        system_prompt_tokens=budget_dict.get("system_prompt_tokens", 4000),
        memory_tokens=budget_dict.get("memory_tokens", 4000),
        react_stack_reserve=budget_dict.get("react_stack_reserve", 10000),
        final_output_reserve=budget_dict.get("final_output_reserve", 16000),
    )

    hc_dict = l1_dict.get("history_collapse", {})
    history_collapse = _build_history_collapse(hc_dict)

    l1 = L1Config(
        budget=budget,
        history_collapse=history_collapse,
        tool_call_collapse_whitelist=l1_dict.get("tool_call_collapse_whitelist", []),
        tool_response_collapse_whitelist=l1_dict.get("tool_response_collapse_whitelist", []),
    )

    l2 = None
    l2_dict = memory_dict.get("l2")
    if l2_dict:
        l2_hc = _build_history_collapse(l2_dict.get("history_collapse", {}))
        l2 = L2Config(
            history_collapse=l2_hc,
            after_collapse_max_length=l2_dict.get("after_collapse_max_length", 94000),
            tool_call_collapse_whitelist=l2_dict.get("tool_call_collapse_whitelist", []),
            tool_response_collapse_whitelist=l2_dict.get("tool_response_collapse_whitelist", []),
            protected_steps=l2_dict.get("protected_steps", 1),
            fallback_strategy=l2_dict.get("fallback_strategy", "abandon"),
        )

    return MemoryConfig(l1=l1, l2=l2)


def _build_history_collapse(hc_dict: Dict[str, Any]) -> HistoryCollapseConfig:
    """构建 HistoryCollapseConfig(与 lite_code 完全一致)。"""
    def _collapse(d: Dict[str, Any]) -> CollapseStrategyConfig:
        return CollapseStrategyConfig(
            type=d.get("type", "none"),
            collapse_prefix_length=d.get("collapse_prefix_length", 200),
        )

    return HistoryCollapseConfig(
        thinking_collapse=_collapse(hc_dict.get("thinking_collapse", {"type": "remove"})),
        tool_call_collapse=_collapse(hc_dict.get("tool_call_collapse", {"type": "none"})),
        tool_response_collapse=_collapse(hc_dict.get("tool_response_collapse", {"type": "prefix", "collapse_prefix_length": 200})),
    )


def _make_app_emit_tool():
    @tool(
        name="app_emit",
        description=(
            "把结构化结果推送到小程序界面。参数 structuredContent 是一个 JSON 对象,"
            "对应小程序 UI 约定的数据模型(整份替换,MVP 全量)。"
        ),
    )
    def app_emit(structuredContent: dict, context=None) -> dict:
        return {"emitted": True, "structuredContent": structuredContent}

    return app_emit


def create_react_agent(manifest: AppManifest, store_dir: Path) -> ReactAgent:
    """按单个小程序 skill 构建 ReactAgent（直接流式，不经 Orchestrator 包装）。"""
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

    workspace_path = str(manifest.root)
    tool_registry = ToolRegistry()

    bash_executor = _CwdBashExecutor(cwd=workspace_path, store_dir=str(store_dir))
    tool_registry.register(BashTool(executor=bash_executor))
    tool_registry.register(TextEditTool(working_directory=workspace_path))
    tool_registry.register(ReadFileTool(working_directory=workspace_path))
    tool_registry.register(ListFilesTool(working_directory=workspace_path))
    tool_registry.register(GrepSearchTool(working_directory=workspace_path))
    tool_registry.register(_make_app_emit_tool())

    memory_config = _build_memory_config(memory_cfg_dict)

    skill_config = SkillConfig(
        skills_config={
            manifest.id: {
                "description": manifest.description or manifest.name,
                "content_file_path": manifest.skill.content_file_path,
                "load_type": "static",
            }
        },
        base_path=str(manifest.root),
    )

    return ReactAgent(ReactAgentConfig(
        llm_client=llm_client,
        tool_registry=tool_registry,
        context_strategy=DefaultContextStrategy(),
        system_prompt=get_system_prompt(extra_context=MINIAPP_EXTRA_CONTEXT),
        max_iterations=agent_cfg.get("max_iterations", 30),
        max_tokens=agent_cfg.get("max_tokens", 8192),
        temperature=agent_cfg.get("temperature", 0.7),
        thinking_level=agent_cfg.get("thinking_level"),
        memory_config=memory_config,
        skill_config=skill_config,
    ))


def run_agent(
    manifest: AppManifest,
    store_dir: Path,
    session_id: str,
    task_id: str,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Iterator[Event]:
    """执行一轮任务:拼历史 + 当前消息 → TaskInput → ReactAgent.run(真流式)。

    直接调用 ReactAgent.run() 而非 OrchestratorAgent.run()，
    因为 OrchestratorAgent 的 AgentNode.execute() 会把所有事件
    攒到列表再回放，导致前端收到的事件全部堆积在一起。
    """
    react_agent = create_react_agent(manifest, store_dir)

    messages: List[Message] = []
    for msg in history or []:
        messages.append(Message.from_role_and_text(msg["role"], msg["content"]))
    messages.append(Message.from_role_and_text("user", user_message))

    task_input = TaskInput(session_id=session_id, task_id=task_id, messages=messages)
    for event in react_agent.run(task_input):
        yield event
