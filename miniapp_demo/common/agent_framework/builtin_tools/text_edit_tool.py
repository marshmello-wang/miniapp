"""
text_edit 工具实现 - 本地文本文件编辑

支持 view / create / str_replace / insert / undo_edit 五种操作，
通过精确文本匹配进行安全的局部编辑。
"""
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

from common.agent_framework.tool_adapter.protocol import ToolSchema, ToolResult
from common.agent_framework.tool_adapter.context import ToolContext


class TextEditTool:
    """
    text_edit 内置工具

    通过精确文本操作管理本地文本文件，支持查看、创建、替换、插入与撤销。
    每个文件维护一份 undo 备份（仅保留最近一次编辑前的版本）。
    """

    MAX_VIEW_SIZE: int = 256 * 1024  # 256 KB

    def __init__(
        self,
        working_directory: str = ".",
        max_view_size: int = MAX_VIEW_SIZE,
    ):
        self._working_dir = os.path.abspath(working_directory)
        self._max_view_size = max_view_size
        # path -> 上一次编辑前的内容（内存级 undo，每个文件仅保留 1 级）
        self._undo_history: Dict[str, str] = {}

    # ── 协议属性 ───────────────────────────────────────

    @property
    def name(self) -> str:
        return "text_edit"

    @property
    def description(self) -> str:
        return (
            "编辑本地文本文件。支持 view（查看）、create（创建）、"
            "str_replace（精确替换）、insert（插入）、undo_edit（撤销）。"
        )

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
                        "description": (
                            "要执行的操作类型。可选值：view / create / "
                            "str_replace / insert / undo_edit"
                        ),
                        "enum": ["view", "create", "str_replace", "insert", "undo_edit"],
                    },
                    "path": {
                        "type": "string",
                        "description": "目标文件路径（相对于工作目录或绝对路径）",
                    },
                    "file_text": {
                        "type": "string",
                        "description": "create 操作时使用的完整文件内容",
                    },
                    "old_str": {
                        "type": "string",
                        "description": "str_replace 操作中需要被替换的原始字符串（必须精确匹配）",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "用于替换或插入的新内容",
                    },
                    "insert_line": {
                        "type": "integer",
                        "description": "insert 操作时的目标行号（从 1 开始），新内容插入到该行之后",
                    },
                },
                "required": ["command", "path"],
                "additionalProperties": False,
            },
        )

    # ── 主入口 ─────────────────────────────────────────

    async def execute(
        self,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        command = parameters.get("command", "")
        path_str = parameters.get("path", "")

        if not command:
            return self._fail("command is required", parameters)
        if not path_str:
            return self._fail("path is required", parameters)

        abs_path = self._resolve_path(path_str)

        dispatch = {
            "view": self._cmd_view,
            "create": self._cmd_create,
            "str_replace": self._cmd_str_replace,
            "insert": self._cmd_insert,
            "undo_edit": self._cmd_undo_edit,
        }

        handler = dispatch.get(command)
        if handler is None:
            return self._fail(
                f"Unknown command: {command}. Must be one of: {', '.join(dispatch)}",
                parameters,
            )

        try:
            return handler(abs_path, parameters)
        except Exception as e:
            return self._fail(f"Execution failed: {e}", parameters)

    # ── 子命令实现 ─────────────────────────────────────

    def _cmd_view(self, abs_path: str, parameters: Dict[str, Any]) -> ToolResult:
        if not os.path.isfile(abs_path):
            return self._fail(f"File not found: {abs_path}", parameters)

        size = os.path.getsize(abs_path)
        if size > self._max_view_size:
            return self._fail(
                f"File too large to view ({size} bytes, limit {self._max_view_size} bytes)",
                parameters,
            )

        content = self._read_file(abs_path)
        numbered = self._add_line_numbers(content)

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=content,
            formatted_data=numbered,
            metadata={"path": abs_path, "size": size, "lines": content.count("\n") + 1},
            parameters=parameters,
        )

    def _cmd_create(self, abs_path: str, parameters: Dict[str, Any]) -> ToolResult:
        file_text = parameters.get("file_text")
        if file_text is None:
            return self._fail("file_text is required for create command", parameters)

        parent = os.path.dirname(abs_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        self._write_file(abs_path, file_text)

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=None,
            formatted_data=f"File created: {abs_path}",
            metadata={"path": abs_path, "size": len(file_text.encode("utf-8"))},
            parameters=parameters,
        )

    def _cmd_str_replace(self, abs_path: str, parameters: Dict[str, Any]) -> ToolResult:
        if not os.path.isfile(abs_path):
            return self._fail(f"File not found: {abs_path}", parameters)

        old_str = parameters.get("old_str")
        if old_str is None:
            return self._fail("old_str is required for str_replace command", parameters)

        new_str = parameters.get("new_str")
        if new_str is None:
            return self._fail("new_str is required for str_replace command", parameters)

        content = self._read_file(abs_path)
        count = content.count(old_str)

        if count == 0:
            return self._fail(
                "old_str not found in file. Make sure it matches the file content exactly, "
                "including whitespace and indentation. Use view command to check the file first.",
                parameters,
            )
        if count > 1:
            return self._fail(
                f"old_str appears {count} times in the file. "
                "It must match exactly once to avoid ambiguous edits. "
                "Include more surrounding context to make it unique.",
                parameters,
            )

        self._save_undo(abs_path, content)
        new_content = content.replace(old_str, new_str, 1)
        self._write_file(abs_path, new_content)

        snippet = self._replacement_snippet(new_content, new_str)

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=None,
            formatted_data=f"Successfully replaced text in {abs_path}\n\n{snippet}",
            metadata={"path": abs_path},
            parameters=parameters,
        )

    def _cmd_insert(self, abs_path: str, parameters: Dict[str, Any]) -> ToolResult:
        if not os.path.isfile(abs_path):
            return self._fail(f"File not found: {abs_path}", parameters)

        insert_line = parameters.get("insert_line")
        if insert_line is None:
            return self._fail("insert_line is required for insert command", parameters)

        new_str = parameters.get("new_str")
        if new_str is None:
            return self._fail("new_str is required for insert command", parameters)

        content = self._read_file(abs_path)
        lines = content.split("\n")
        total_lines = len(lines)

        if insert_line < 0 or insert_line > total_lines:
            return self._fail(
                f"insert_line {insert_line} is out of range (0..{total_lines}). "
                "Use 0 to insert at the beginning of the file.",
                parameters,
            )

        self._save_undo(abs_path, content)

        insert_lines = new_str.split("\n")
        new_lines = lines[:insert_line] + insert_lines + lines[insert_line:]
        new_content = "\n".join(new_lines)
        self._write_file(abs_path, new_content)

        snippet = self._insert_snippet(new_lines, insert_line, len(insert_lines))

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=None,
            formatted_data=f"Successfully inserted text at line {insert_line} in {abs_path}\n\n{snippet}",
            metadata={"path": abs_path, "insert_line": insert_line},
            parameters=parameters,
        )

    def _cmd_undo_edit(self, abs_path: str, parameters: Dict[str, Any]) -> ToolResult:
        if abs_path not in self._undo_history:
            return self._fail(
                f"No undo history for {abs_path}. Only the most recent edit can be undone.",
                parameters,
            )

        previous_content = self._undo_history.pop(abs_path)
        self._write_file(abs_path, previous_content)

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=None,
            formatted_data=f"Successfully undid the last edit to {abs_path}",
            metadata={"path": abs_path},
            parameters=parameters,
        )

    # ── 内部工具方法 ───────────────────────────────────

    def _resolve_path(self, path_str: str) -> str:
        """将用户输入路径解析为绝对路径"""
        if os.path.isabs(path_str):
            return os.path.normpath(path_str)
        return os.path.normpath(os.path.join(self._working_dir, path_str))

    def _read_file(self, abs_path: str) -> str:
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()

    def _write_file(self, abs_path: str, content: str) -> None:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _save_undo(self, abs_path: str, content: str) -> None:
        """保存当前内容用于 undo（仅保留最近 1 次）"""
        self._undo_history[abs_path] = content

    def _add_line_numbers(self, content: str) -> str:
        lines = content.split("\n")
        width = len(str(len(lines)))
        numbered = [f"{i + 1:>{width}}|{line}" for i, line in enumerate(lines)]
        return "\n".join(numbered)

    def _replacement_snippet(self, full_content: str, new_str: str, context: int = 3) -> str:
        """生成替换结果的上下文片段"""
        lines = full_content.split("\n")
        new_lines = new_str.split("\n")

        idx = full_content.find(new_str)
        if idx == -1:
            return ""
        start_line = full_content[:idx].count("\n")
        end_line = start_line + len(new_lines) - 1

        snippet_start = max(0, start_line - context)
        snippet_end = min(len(lines), end_line + context + 1)

        width = len(str(snippet_end))
        snippet_lines = [
            f"{i + 1:>{width}}|{lines[i]}"
            for i in range(snippet_start, snippet_end)
        ]
        return "\n".join(snippet_lines)

    def _insert_snippet(self, lines: list, insert_line: int, insert_count: int, context: int = 3) -> str:
        """生成插入结果的上下文片段"""
        snippet_start = max(0, insert_line - context)
        snippet_end = min(len(lines), insert_line + insert_count + context)

        width = len(str(snippet_end))
        snippet_lines = [
            f"{i + 1:>{width}}|{lines[i]}"
            for i in range(snippet_start, snippet_end)
        ]
        return "\n".join(snippet_lines)

    def _fail(self, error: str, parameters: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            success=False,
            data=None,
            error=error,
            parameters=parameters,
        )
