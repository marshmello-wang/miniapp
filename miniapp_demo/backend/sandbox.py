"""本地 sandbox:用子进程执行小程序脚本。

约定:
- cwd = 小程序根目录(可 import 自己的模块 / 读取相对资源)。
- 环境变量 MINIAPP_STORE = 该 session 的业务 store 目录(脚本读写业务数据)。
- 入参通过 stdin(JSON)和环境变量 MINIAPP_ARGS(JSON)同时提供。
- 可信元数据通过每次调用独立的 MINIAPP_RESULT_PATH 结果文件返回。
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from . import script_metadata


@dataclass
class ScriptResult:
    exit_code: int
    stdout: str
    stderr: str
    miniapp_metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.error is None


def _script_sdk_path() -> Path:
    return Path(__file__).resolve().parents[1] / "script_sdk"


def _with_pythonpath(env: Dict[str, str], path: Path) -> None:
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        os.pathsep.join((str(path), existing)) if existing else str(path)
    )


def _subprocess_group_kwargs() -> Dict[str, bool]:
    if os.name == "posix":
        return {"start_new_session": True}
    return {}


async def _terminate_process_group(
    process: asyncio.subprocess.Process,
    process_group: Optional[int] = None,
) -> None:
    try:
        if os.name == "posix":
            target_group = process_group or process.pid
            if target_group != os.getpgrp():
                os.killpg(target_group, signal.SIGKILL)
            elif process.returncode is None:
                process.kill()
        elif process.returncode is None:
            process.kill()
    except ProcessLookupError:
        pass
    await process.wait()


async def run_script(
    script_path: Path,
    cwd: Path,
    store_dir: Path,
    arguments: Dict[str, Any],
    timeout: float = 30.0,
) -> ScriptResult:
    store_dir.mkdir(parents=True, exist_ok=True)
    args_json = json.dumps(arguments or {}, ensure_ascii=False)

    with script_metadata.result_file() as result_path:
        env = dict(os.environ)
        env["MINIAPP_STORE"] = str(store_dir)
        env["MINIAPP_ARGS"] = args_json
        env["MINIAPP_RESULT_PATH"] = str(result_path)
        _with_pythonpath(env, _script_sdk_path())

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            cwd=str(cwd),
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **_subprocess_group_kwargs(),
        )
        process_group = proc.pid if os.name == "posix" else None
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=args_json.encode("utf-8")), timeout=timeout
            )
        except asyncio.TimeoutError:
            await _terminate_process_group(proc, process_group)
            return ScriptResult(
                exit_code=124,
                stdout="",
                stderr="timeout",
                error="script timeout",
            )
        except asyncio.CancelledError:
            await _terminate_process_group(proc, process_group)
            raise

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        exit_code = proc.returncode or 0
        if exit_code != 0:
            return ScriptResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                error=stderr.strip() or f"script exited with code {exit_code}",
            )

        metadata = None
        try:
            if result_path.stat().st_size:
                metadata = script_metadata.parse_result_file(result_path)
        except (script_metadata.MetadataError, OSError) as exc:
            return ScriptResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                error=f"invalid script metadata: {exc}",
            )
        return ScriptResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            miniapp_metadata=metadata,
        )
