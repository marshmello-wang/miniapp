"""
工具注册中心 - 统一管理所有工具
"""
from typing import Dict, List, Optional, Any
from .protocol import Tool


class ToolRegistry:
    """
    工具注册中心
    
    统一管理所有工具（本地工具和 MCP 工具）
    """
    
    def __init__(self):
        """初始化工具注册中心"""
        self._tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """
        注册工具
        
        Args:
            tool: 工具对象
        
        Raises:
            ValueError: 如果工具名称已存在
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name} already registered")
        self._tools[tool.name] = tool
    
    def unregister(self, tool_name: str) -> None:
        """
        注销工具
        
        Args:
            tool_name: 工具名称
        """
        self._tools.pop(tool_name, None)
    
    def get(self, tool_name: str) -> Optional[Tool]:
        """
        获取工具
        
        Args:
            tool_name: 工具名称
        
        Returns:
            工具对象，如果不存在则返回 None
        """
        return self._tools.get(tool_name)
    
    def list_tools(self) -> List[Tool]:
        """
        列出所有工具
        
        Returns:
            工具列表
        """
        return list(self._tools.values())
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """
        获取所有工具的 schema（用于传给模型）
        
        Returns:
            工具 schema 列表
        """
        return [tool.schema.to_json_schema() for tool in self._tools.values()]
    
    def clear(self) -> None:
        """清空所有已注册的工具"""
        self._tools.clear()
    
    def has_tool(self, tool_name: str) -> bool:
        """
        检查工具是否已注册
        
        Args:
            tool_name: 工具名称
        
        Returns:
            是否已注册
        """
        return tool_name in self._tools
    
    def __len__(self) -> int:
        """返回已注册工具的数量"""
        return len(self._tools)

