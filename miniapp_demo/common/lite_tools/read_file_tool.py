"""
read_file 工具 - 读取工作区中的文件内容
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

from common.agent_framework.tool_adapter.protocol import ToolSchema, ToolResult
from common.agent_framework.tool_adapter.context import ToolContext


class ReadFileTool:
    """读取文件内容，支持行号范围"""

    MAX_FILE_SIZE = 512 * 1024  # 512KB

    def __init__(self, working_directory: str = "."):
        self._working_dir = os.path.abspath(working_directory)

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "读取指定文件的内容。支持通过 start_line/end_line 指定行范围。"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对于工作目录或绝对路径）",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（1-based，可选）",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号（1-based，包含，可选）",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        rel_path = parameters.get("path", "")
        if not rel_path:
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error="path is required", parameters=parameters,
            )

        file_path = self._resolve_path(rel_path)
        if not file_path:
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error=f"Path escapes working directory: {rel_path}",
                parameters=parameters,
            )

        path = Path(file_path)
        if not path.exists():
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error=f"File not found: {rel_path}", parameters=parameters,
            )
        if not path.is_file():
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error=f"Not a file: {rel_path}", parameters=parameters,
            )
        if path.stat().st_size > self.MAX_FILE_SIZE:
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error=f"File too large ({path.stat().st_size} bytes). Max: {self.MAX_FILE_SIZE}",
                parameters=parameters,
            )

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error="Cannot read binary file", parameters=parameters,
            )

        start_line = parameters.get("start_line")
        end_line = parameters.get("end_line")

        if start_line is not None or end_line is not None:
            lines = content.splitlines(keepends=True)
            total = len(lines)
            start = max(0, (start_line - 1)) if start_line else 0
            end = min(total, end_line) if end_line else total
            selected = lines[start:end]
            numbered = "".join(
                f"{start + i + 1:6}|{line}" for i, line in enumerate(selected)
            )
            formatted = f"File: {rel_path} (lines {start+1}-{end} of {total})\n{numbered}"
        else:
            lines = content.splitlines(keepends=True)
            total = len(lines)
            numbered = "".join(f"{i+1:6}|{line}" for i, line in enumerate(lines))
            formatted = f"File: {rel_path} ({total} lines)\n{numbered}"

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"content": content, "total_lines": total},
            formatted_data=formatted,
            parameters=parameters,
        )

    def _resolve_path(self, rel_path: str) -> Optional[str]:
        """解析路径，确保不逃逸工作目录"""
        if os.path.isabs(rel_path):
            resolved = os.path.realpath(rel_path)
        else:
            resolved = os.path.realpath(os.path.join(self._working_dir, rel_path))

        if not resolved.startswith(self._working_dir):
            return None
        return resolved
