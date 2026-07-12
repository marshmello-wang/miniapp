"""
read_expire_history 工具 - 读取被 prefix_ref 策略折叠的完整内容

当 L1/L2 使用 prefix_ref 折叠策略时，被折叠的完整内容存入 ExpiredContentStore，
消息中留下 ref_id 引用。Agent 可通过此工具按 ref_id 召回完整内容。
"""
from typing import Any, Dict, Optional

from common.agent_framework.context_strategy.memory.store import ExpiredContentStore
from common.agent_framework.tool_adapter.context import ToolContext
from common.agent_framework.tool_adapter.protocol import ToolResult, ToolSchema


class ReadExpireHistoryTool:
    """
    读取被折叠至外部存储的历史内容

    需要在初始化时注入 ExpiredContentStore 实例，
    与 ContextMemoryHelper 共享同一个 store。
    """

    def __init__(self, store: ExpiredContentStore):
        self._store = store

    @property
    def name(self) -> str:
        return "read_expire_history"

    @property
    def description(self) -> str:
        return (
            "读取被折叠至外部存储的历史内容。"
            "当消息中出现 ref_id 引用时，使用此工具传入 ref_id 即可召回完整原文。"
        )

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            schema={
                "type": "object",
                "properties": {
                    "ref_id": {
                        "type": "string",
                        "description": "折叠时生成的引用 ID，如 tool_a2rf、think_b3e1",
                    },
                },
                "required": ["ref_id"],
            },
        )

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        ref_id = parameters.get("ref_id", "")
        if not ref_id:
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error="ref_id is required",
                parameters=parameters,
            )

        content = self._store.load(ref_id)
        if content is None:
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error=f"ref_id '{ref_id}' not found in store",
                parameters=parameters,
            )

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"ref_id": ref_id, "content": content},
            formatted_data=content,
            metadata={"ref_id": ref_id, "content_length": len(content)},
            parameters=parameters,
        )
