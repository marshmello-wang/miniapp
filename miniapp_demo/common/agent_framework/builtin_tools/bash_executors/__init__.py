"""
Bash Executors - BashExecutor 协议的具体实现

提供不同执行后端的实现，由调用方按需选择注入 BashTool。
"""

from .local import LocalBashExecutor

__all__ = [
    "LocalBashExecutor",
]
