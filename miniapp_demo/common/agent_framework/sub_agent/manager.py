"""
Sub Agent 管理器 - 编排子 Agent 的派遣与执行
"""
from typing import List
from uuid import uuid4

from common.agent_framework.user_interface.inputs import TaskInput, Message
from common.agent_framework.user_interface.content_blocks import TextBlock

from .protocol import SubAgentDefinition, SubAgentResult
from .registry import SubAgentRegistry


class SubAgentManager:
    """
    子 Agent 管理器

    负责：
    - 生成可用子 Agent 的候选列表文本（注入 system prompt）
    - 派遣子 Agent 执行任务并收集结果
    """

    def __init__(self, registry: SubAgentRegistry):
        self._registry = registry

    def get_candidates_prompt(self) -> str:
        """
        生成可用子 Agent 候选列表文本，用于注入到 system prompt。

        Returns:
            格式化的候选列表文本，如果没有子 Agent 则返回空字符串
        """
        agents = self._registry.list_all()
        if not agents:
            return ""

        lines = [
            "## 可用子 Agent",
            "",
            "当需要专家帮助时，使用 create_sub_agent 工具派遣子 Agent 执行子任务。",
            "可用的子 Agent：",
            "",
        ]
        for defn in agents:
            lines.append(f"- **{defn.name}**: {defn.description}")

        return "\n".join(lines)

    async def dispatch(self, agent_name: str, message: str, session_id: str) -> SubAgentResult:
        """
        派遣一个子 Agent 执行任务

        Args:
            agent_name: 子 Agent 名称
            message: 发送给子 Agent 的消息
            session_id: 父级 session_id（用于生成子 session_id）

        Returns:
            SubAgentResult: 执行结果
        """
        defn = self._registry.get(agent_name)
        if defn is None:
            available = [d.name for d in self._registry.list_all()]
            return SubAgentResult(
                success=False,
                error=f"Sub agent '{agent_name}' not found. Available: {available}",
                agent_name=agent_name,
            )

        sub_session_id = f"{session_id}-sub-{agent_name}-{uuid4().hex[:8]}"
        sub_task_id = f"sub-{agent_name}-{uuid4().hex[:8]}"

        task_input = TaskInput(
            session_id=sub_session_id,
            task_id=sub_task_id,
            messages=[Message.from_role_and_text("user", message)],
        )

        try:
            return await self._run_agent(defn, task_input)
        except Exception as e:
            return SubAgentResult(
                success=False,
                error=f"Sub agent '{agent_name}' execution failed: {str(e)}",
                agent_name=agent_name,
            )

    async def _run_agent(self, defn: SubAgentDefinition, task_input: TaskInput) -> SubAgentResult:
        """通过 run_async 运行子 Agent，避免嵌套 event loop"""
        agent = defn.agent
        final_text_parts: List[str] = []
        error_parts: List[str] = []

        async for event in agent.run_async(task_input):
            if event.event_type == "reasoning":
                for block in event.content:
                    if isinstance(block, TextBlock) and block.text:
                        final_text_parts.append(block.text)
            elif event.event_type == "error":
                for block in event.content:
                    if isinstance(block, TextBlock) and block.text:
                        error_parts.append(block.text)

        if error_parts and not final_text_parts:
            return SubAgentResult(
                success=False,
                error="\n".join(error_parts),
                agent_name=defn.name,
            )

        return SubAgentResult(
            success=True,
            output="\n".join(final_text_parts),
            agent_name=defn.name,
        )
