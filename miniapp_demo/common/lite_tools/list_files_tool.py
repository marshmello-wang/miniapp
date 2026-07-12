"""
list_files 工具 - 列出工作区中的文件和目录
"""
import fnmatch
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.agent_framework.tool_adapter.protocol import ToolSchema, ToolResult
from common.agent_framework.tool_adapter.context import ToolContext


DEFAULT_IGNORE = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".DS_Store", ".idea", ".vscode", "dist", "build",
}


class ListFilesTool:
    """列出目录中的文件，支持 glob 过滤和递归"""

    MAX_RESULTS = 500

    def __init__(self, working_directory: str = "."):
        self._working_dir = os.path.abspath(working_directory)

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return "列出指定目录下的文件和子目录。支持 glob 模式过滤和递归搜索。"

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
                        "description": "要列出的目录路径（相对于工作目录，默认 '.'）",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob 过滤模式（如 '*.py'、'**/*.ts'）",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归列出子目录（默认 false）",
                    },
                },
            },
        )

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        rel_path = parameters.get("path", ".")
        pattern = parameters.get("pattern")
        recursive = parameters.get("recursive", False)

        target_dir = self._resolve_path(rel_path)
        if not target_dir:
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error=f"Path escapes working directory: {rel_path}",
                parameters=parameters,
            )

        path = Path(target_dir)
        if not path.exists():
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error=f"Directory not found: {rel_path}", parameters=parameters,
            )
        if not path.is_dir():
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error=f"Not a directory: {rel_path}", parameters=parameters,
            )

        results: List[str] = []

        if pattern and recursive:
            for item in path.rglob(pattern):
                if self._should_ignore(item):
                    continue
                rel = str(item.relative_to(Path(self._working_dir)))
                suffix = "/" if item.is_dir() else ""
                results.append(f"{rel}{suffix}")
        elif pattern:
            for item in path.glob(pattern):
                if self._should_ignore(item):
                    continue
                rel = str(item.relative_to(Path(self._working_dir)))
                suffix = "/" if item.is_dir() else ""
                results.append(f"{rel}{suffix}")
        elif recursive:
            for item in path.rglob("*"):
                if self._should_ignore(item):
                    continue
                rel = str(item.relative_to(Path(self._working_dir)))
                suffix = "/" if item.is_dir() else ""
                results.append(f"{rel}{suffix}")
        else:
            try:
                items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except PermissionError:
                return ToolResult(
                    tool_name=self.name, success=False, data=None,
                    error=f"Permission denied: {rel_path}", parameters=parameters,
                )
            for item in items:
                if item.name in DEFAULT_IGNORE:
                    continue
                rel = str(item.relative_to(Path(self._working_dir)))
                suffix = "/" if item.is_dir() else ""
                results.append(f"{rel}{suffix}")

        truncated = len(results) > self.MAX_RESULTS
        results = results[: self.MAX_RESULTS]

        formatted_lines = results.copy()
        if truncated:
            formatted_lines.append(f"... (truncated, showing {self.MAX_RESULTS} of more results)")

        formatted = f"Directory: {rel_path}\n" + "\n".join(formatted_lines)

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"files": results, "truncated": truncated},
            formatted_data=formatted,
            parameters=parameters,
        )

    def _resolve_path(self, rel_path: str) -> Optional[str]:
        if os.path.isabs(rel_path):
            resolved = os.path.realpath(rel_path)
        else:
            resolved = os.path.realpath(os.path.join(self._working_dir, rel_path))
        if not resolved.startswith(self._working_dir):
            return None
        return resolved

    def _should_ignore(self, path: Path) -> bool:
        parts = path.parts
        return any(part in DEFAULT_IGNORE for part in parts)
