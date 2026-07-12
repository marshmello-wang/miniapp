"""
工具执行器 - 负责执行工具并处理结果
"""
from typing import Dict, Any, Optional
from .protocol import ToolResult
from .context import ToolContext
from .registry import ToolRegistry


class ToolExecutor:
    """
    工具执行器
    
    负责执行工具并处理结果
    """
    
    def __init__(self, registry: ToolRegistry):
        """
        初始化工具执行器
        
        Args:
            registry: 工具注册中心
        """
        self.registry = registry
    
    async def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None,
        call_id: Optional[str] = None
    ) -> ToolResult:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            parameters: 工具参数
            context: 执行上下文
            call_id: 工具调用 ID（可选）
        
        Returns:
            ToolResult: 工具执行结果
        """
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=f"Tool {tool_name} not found",
                parameters=parameters,
                call_id=call_id
            )
        
        try:
            result = await tool.execute(parameters, context)
            
            # 设置 call_id
            if call_id:
                result.call_id = call_id
            
            return result
        
        except Exception as e:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=f"Tool execution failed: {str(e)}",
                parameters=parameters,
                call_id=call_id
            )

