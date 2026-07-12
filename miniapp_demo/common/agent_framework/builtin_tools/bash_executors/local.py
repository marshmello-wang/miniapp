"""
LocalBashExecutor - 本地 subprocess 执行后端

基于 asyncio.create_subprocess_shell 实现，适用于本地容器环境。
"""
import asyncio

from common.agent_framework.builtin_tools.bash_tool import BashResult


class LocalBashExecutor:
    """
    本地 Bash 执行器

    使用 asyncio subprocess 在本地执行 bash 命令。
    超时时 kill 进程并抛出 asyncio.TimeoutError（由 BashTool 层统一处理）。
    """

    async def execute(self, command: str, timeout: float) -> BashResult:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise

        return BashResult(
            exit_code=process.returncode or 0,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
        )
