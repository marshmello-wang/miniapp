"""
create_sub_agent 工具实现 - 供模型按名派遣预注册的子 Agent
"""
from typing import Dict, Any, Optional

from common.agent_framework.tool_adapter.protocol import ToolSchema, ToolResult
from common.agent_framework.tool_adapter.context import ToolContext
from common.agent_framework.sub_agent.manager import SubAgentManager


class CreateSubAgentTool:
    """
    create_sub_agent 工具

    模型调用此工具来派遣一个预注册的子 Agent 执行子任务。
    子 Agent 会独立运行自己的 ReAct 循环，最终文本输出作为工具结果返回。
    """

    def __init__(self, sub_agent_manager: SubAgentManager, session_id: str = ""):
        self._manager = sub_agent_manager
        self._session_id = session_id

    def set_session_id(self, session_id: str) -> None:
        """设置当前 session_id（由 ReactAgent 在运行时调用）"""
        self._session_id = session_id

    @property
    def name(self) -> str:
        return "create_sub_agent"

    @property
    def description(self) -> str:
        return (
            "派遣一个预注册的子 Agent 来执行子任务。"
            "传入子 Agent 名称和任务消息，子 Agent 会独立完成任务并返回结果。"
        )

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            schema={
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "要派遣的子 Agent 名称",
                    },
                    "message": {
                        "type": "string",
                        "description": "发送给子 Agent 的任务描述",
                    },
                },
                "required": ["agent_name", "message"],
            },
        )

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        agent_name = parameters.get("agent_name", "")
        message = parameters.get("message", "")

        if not agent_name:
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error="agent_name is required",
                parameters=parameters,
            )
        if not message:
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error="message is required",
                parameters=parameters,
            )

        result = await self._manager.dispatch(
            agent_name=agent_name,
            message=message,
            session_id=self._session_id,
        )

        if not result.success:
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error=result.error,
                parameters=parameters,
            )

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=result.output,
            formatted_data=result.output,
            metadata={"agent_name": agent_name},
            parameters=parameters,
        )
