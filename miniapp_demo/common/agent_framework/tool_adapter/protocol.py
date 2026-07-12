"""
协议接口定义 - 定义工具的核心协议
"""
from typing import Protocol, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ToolSchema:
    """
    工具 Schema 定义，直接采用 JSON Schema 结构声明（参考 MCP style）
    """
    name: str
    description: str
    schema: Dict[str, Any]  # 完整的 JSON Schema，描述所有参数及结构

    def to_json_schema(self) -> Dict[str, Any]:
        """
        返回标准的 JSON Schema 格式（参数部分通常放在 'properties' 下，并设置 'required' 列表）。
        对于工具协议，schema 应包括 type/object、properties, required 等字段。
        """
        json_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": self.schema,
        }
        return json_schema


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_name: str  # 工具名称
    success: bool
    data: Any  # 原始返回数据
    formatted_data: Optional[str] = None  # 格式化后的数据（用于传给模型）
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # 元数据（如执行时间、token数等）
    parameters: Optional[Dict[str, Any]] = None  # 工具请求的原始参数/内容
    call_id: Optional[str] = None  # 本次工具调用唯一标识


class Tool(Protocol):
    """工具协议接口"""
    
    @property
    def name(self) -> str:
        """工具名称"""
        ...
    
    @property
    def description(self) -> str:
        """工具描述"""
        ...
    
    @property
    def schema(self) -> ToolSchema:
        """工具的参数 Schema"""
        ...
    
    async def execute(
        self, 
        parameters: Dict[str, Any],
        context: Optional["ToolContext"] = None
    ) -> ToolResult:
        """
        执行工具
        
        Args:
            parameters: 工具参数
            context: 执行上下文（可选，用于工具间状态共享）
        
        Returns:
            ToolResult: 工具执行结果
        """
        ...

