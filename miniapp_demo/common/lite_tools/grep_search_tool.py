"""
grep_search 工具 - 在工作区中搜索文本
"""
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from common.agent_framework.tool_adapter.protocol import ToolSchema, ToolResult
from common.agent_framework.tool_adapter.context import ToolContext


BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".exe", ".dll", ".so", ".dylib",
    ".pyc", ".pyo", ".class", ".o",
}

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".DS_Store", ".idea", ".vscode", "dist", "build",
}


class GrepSearchTool:
    """在工作区内搜索文本内容"""

    MAX_RESULTS = 100
    MAX_LINE_LENGTH = 500

    def __init__(self, working_directory: str = "."):
        self._working_dir = os.path.abspath(working_directory)

    @property
    def name(self) -> str:
        return "grep_search"

    @property
    def description(self) -> str:
        return "在工作区文件中搜索文本或正则表达式，返回匹配的文件和行。"

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式（支持正则表达式）",
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索的起始目录（相对路径，默认 '.'）",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "文件名过滤 glob（如 '*.py'）",
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "是否区分大小写（默认 true）",
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        pattern_str = parameters.get("pattern", "")
        if not pattern_str:
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error="pattern is required", parameters=parameters,
            )

        rel_path = parameters.get("path", ".")
        file_pattern = parameters.get("file_pattern")
        case_sensitive = parameters.get("case_sensitive", True)

        target_dir = self._resolve_path(rel_path)
        if not target_dir:
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error=f"Path escapes working directory: {rel_path}",
                parameters=parameters,
            )

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern_str, flags)
        except re.error as e:
            return ToolResult(
                tool_name=self.name, success=False, data=None,
                error=f"Invalid regex: {e}", parameters=parameters,
            )

        matches: List[Dict[str, Any]] = []
        root = Path(target_dir)

        for file_path in self._iter_files(root, file_pattern):
            file_matches = self._search_file(file_path, regex)
            for line_no, line_text in file_matches:
                rel_file = str(file_path.relative_to(Path(self._working_dir)))
                matches.append({
                    "file": rel_file,
                    "line": line_no,
                    "text": line_text[:self.MAX_LINE_LENGTH],
                })
                if len(matches) >= self.MAX_RESULTS:
                    break
            if len(matches) >= self.MAX_RESULTS:
                break

        truncated = len(matches) >= self.MAX_RESULTS
        formatted_lines = []
        for m in matches:
            formatted_lines.append(f"{m['file']}:{m['line']}: {m['text']}")

        if truncated:
            formatted_lines.append(f"\n... (showing first {self.MAX_RESULTS} results)")

        summary = f"Found {len(matches)} match(es) for '{pattern_str}'"
        formatted = summary + "\n" + "\n".join(formatted_lines) if formatted_lines else summary

        return ToolResult(
            tool_name=self.name,
            success=True,
            data={"matches": matches, "truncated": truncated, "count": len(matches)},
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

    def _iter_files(self, root: Path, file_pattern: Optional[str] = None):
        """递归迭代可搜索的文件"""
        for item in root.rglob(file_pattern or "*"):
            if not item.is_file():
                continue
            if any(part in IGNORE_DIRS for part in item.parts):
                continue
            if item.suffix.lower() in BINARY_EXTENSIONS:
                continue
            yield item

    def _search_file(self, file_path: Path, regex: re.Pattern) -> List[Tuple[int, str]]:
        """在单个文件中搜索，返回 (行号, 行内容) 列表"""
        results = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_no, line in enumerate(f, start=1):
                    if regex.search(line):
                        results.append((line_no, line.rstrip("\n\r")))
        except (PermissionError, OSError):
            pass
        return results
