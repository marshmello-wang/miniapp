"""
Tool Adapter - 工具适配器模块

提供统一的工具接口，支持本地函数和 MCP 工具的集成
"""

# 协议和数据结构
from .protocol import Tool, ToolSchema, ToolResult
from .context import ToolContext

# 本地工具
from .decorators import tool
from .local_tool import LocalTool

# MCP 工具
from .mcp_adapter import MCPToolAdapter
from .mcp_tool import MCPTool

# 工具管理
from .registry import ToolRegistry
from .executor import ToolExecutor


__all__ = [
    # 协议
    "Tool",
    "ToolSchema",
    "ToolResult",
    "ToolContext",
    
    # 本地工具
    "tool",
    "LocalTool",
    
    # MCP 工具
    "MCPToolAdapter",
    "MCPTool",
    
    # 工具管理
    "ToolRegistry",
    "ToolExecutor",
]

