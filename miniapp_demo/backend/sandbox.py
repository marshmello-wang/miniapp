"""本地 sandbox:用子进程执行小程序脚本。

约定:
- cwd = 小程序根目录(可 import 自己的模块 / 读取相对资源)。
- 环境变量 MINIAPP_STORE = 该 session 的业务 store 目录(脚本读写业务数据)。
- 入参通过 stdin(JSON)和环境变量 MINIAPP_ARGS(JSON)同时提供。
- 脚本约定向 stdout 打印一段 JSON,形如 {"structuredContent": {...}}。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass
class ScriptResult:
    exit_code: int
    structured_content: Dict[str, Any]
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _parse_structured(stdout: str) -> Dict[str, Any]:
    stdout = stdout.strip()
    if not stdout:
        return {}
    # 优先整体解析
    try:
        obj = json.loads(stdout)
        return obj.get("structuredContent", obj) if isinstance(obj, dict) else {"value": obj}
    except json.JSONDecodeError:
        pass
    # 退回:取最后一行非空 JSON
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            return obj.get("structuredContent", obj) if isinstance(obj, dict) else {"value": obj}
        except json.JSONDecodeError:
            continue
    return {"stdout": stdout}


async def run_script(
    script_path: Path,
    cwd: Path,
    store_dir: Path,
    arguments: Dict[str, Any],
    timeout: float = 30.0,
) -> ScriptResult:
    store_dir.mkdir(parents=True, exist_ok=True)
    args_json = json.dumps(arguments or {}, ensure_ascii=False)

    env = dict(os.environ)
    env["MINIAPP_STORE"] = str(store_dir)
    env["MINIAPP_ARGS"] = args_json

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script_path),
        cwd=str(cwd),
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=args_json.encode("utf-8")), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return ScriptResult(
            exit_code=124,
            structured_content={"error": "script timeout"},
            stdout="",
            stderr="timeout",
        )

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    structured = _parse_structured(stdout) if proc.returncode == 0 else {"error": stderr or "script failed"}
    return ScriptResult(
        exit_code=proc.returncode or 0,
        structured_content=structured,
        stdout=stdout,
        stderr=stderr,
    )
