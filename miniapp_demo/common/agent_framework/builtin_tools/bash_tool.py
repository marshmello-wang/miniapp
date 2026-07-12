"""
bash 工具实现 - 在容器内执行 bash 命令

通过 BashExecutor Protocol 抽象执行后端，支持本地/远程容器。
工具层负责 timeout 熔断和输出格式化。
"""
import asyncio
from typing import Dict, Any, Optional, runtime_checkable
from dataclasses import dataclass
from typing import Protocol

from common.agent_framework.tool_adapter.protocol import Tool, ToolSchema, ToolResult
from common.agent_framework.tool_adapter.context import ToolContext


@dataclass
class BashResult:
    """Bash 命令执行结果"""
    exit_code: int
    stdout: str
    stderr: str


@runtime_checkable
class BashExecutor(Protocol):
    """
    Bash 执行后端协议

    调用方注入具体实现（本地 subprocess、Docker exec、SSH、K8s exec 等）。
    """

    async def execute(self, command: str, timeout: float) -> BashResult:
        """
        执行 bash 命令

        Args:
            command: 要执行的 bash 命令
            timeout: 超时时间（秒）

        Returns:
            BashResult: 命令执行结果

        Raises:
            asyncio.TimeoutError: 执行超时时由调用方处理
        """
        ...


class BashTool:
    """
    Bash 内置工具

    在容器内执行 bash 命令，通过注入的 BashExecutor 实现具体执行逻辑。
    工具层负责 timeout 熔断和输出截断/格式化。
    """

    DEFAULT_TIMEOUT: float = 60.0
    MAX_OUTPUT_LENGTH: int = 50000

    def __init__(
        self,
        executor: BashExecutor,
        default_timeout: float = DEFAULT_TIMEOUT,
        max_output_length: int = MAX_OUTPUT_LENGTH,
    ):
        self._executor = executor
        self._default_timeout = default_timeout
        self._max_output_length = max_output_length

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return "在容器内执行 bash 命令，返回 stdout、stderr 和 exit code。"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 bash 命令",
                    },
                    "timeout": {
                        "type": "number",
                        "description": f"超时时间（秒），默认 {self._default_timeout}s",
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        command = parameters.get("command", "")
        if not command:
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error="command is required",
                parameters=parameters,
            )

        timeout = float(parameters.get("timeout", self._default_timeout))

        try:
            result = await asyncio.wait_for(
                self._executor.execute(command=command, timeout=timeout),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error=f"Command timed out after {timeout}s",
                metadata={"timeout": timeout, "command": command},
                parameters=parameters,
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                success=False,
                data=None,
                error=f"Execution failed: {str(e)}",
                parameters=parameters,
            )

        stdout = self._truncate(result.stdout)
        stderr = self._truncate(result.stderr)
        formatted = self._format_output(result.exit_code, stdout, stderr)

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={
                "exit_code": result.exit_code,
                "stdout": stdout,
                "stderr": stderr,
            },
            formatted_data=formatted,
            metadata={"exit_code": result.exit_code},
            parameters=parameters,
        )

    def _truncate(self, text: str) -> str:
        if len(text) <= self._max_output_length:
            return text
        half = self._max_output_length // 2
        return text[:half] + f"\n\n... [truncated {len(text) - self._max_output_length} chars] ...\n\n" + text[-half:]

    def _format_output(self, exit_code: int, stdout: str, stderr: str) -> str:
        parts = [f"Exit code: {exit_code}"]
        if stdout:
            parts.append(f"--- stdout ---\n{stdout}")
        if stderr:
            parts.append(f"--- stderr ---\n{stderr}")
        return "\n".join(parts)
