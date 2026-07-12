"""
本地工具实现类
"""
import inspect
import asyncio
from typing import Callable, Optional, Dict, Any, List
from .protocol import Tool, ToolSchema, ToolResult
from .context import ToolContext


class LocalTool:
    """
    本地工具实现类，实现 Tool Protocol
    
    将 Python 函数包装为符合协议的工具
    """
    
    def __init__(
        self,
        func: Callable,
        name: str,
        description: str,
        parameters: List[Dict[str, Any]],
        result_formatter: Optional[Callable[[Any], str]] = None,
        max_result_length: Optional[int] = None
    ):
        """
        初始化本地工具
        
        Args:
            func: 函数对象
            name: 工具名称
            description: 工具描述
            parameters: 参数 schema 列表
            result_formatter: 结果格式化函数（可选）
            max_result_length: 结果最大长度限制
        """
        self._func = func
        self._name = name
        self._description = description
        self._parameters = parameters
        self._result_formatter = result_formatter
        self._max_result_length = max_result_length
        
        # 检查函数是否是异步的
        self._is_async = inspect.iscoroutinefunction(func)
    
    @property
    def name(self) -> str:
        """工具名称"""
        return self._name
    
    @property
    def description(self) -> str:
        """工具描述"""
        return self._description
    
    @property
    def schema(self) -> ToolSchema:
        """工具的参数 Schema"""
        # 将参数列表转换为 JSON Schema 格式
        properties = {}
        required = []
        
        for param in self._parameters:
            param_name = param["name"]
            # 保留参数中除内部字段外的所有 JSON Schema 字段
            # 例如 items、enum、format、minimum 等
            param_schema = {
                k: v
                for k, v in param.items()
                if k not in {"name", "required", "annotation"}
            }
            if "type" not in param_schema:
                param_schema["type"] = "string"
            
            properties[param_name] = param_schema
            
            # 添加到 required 列表
            if param.get("required", True):
                required.append(param_name)
        
        json_schema = {
            "type": "object",
            "properties": properties,
        }
        
        if required:
            json_schema["required"] = required
        
        return ToolSchema(
            name=self._name,
            description=self._description,
            schema=json_schema
        )
    
    async def execute(
        self,
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult:
        """
        执行工具
        
        Args:
            parameters: 工具参数
            context: 执行上下文
        
        Returns:
            ToolResult: 工具执行结果
        """
        try:
            # 准备函数参数
            func_kwargs = parameters.copy()
            
            # 检查函数签名是否接受 context 参数
            sig = inspect.signature(self._func)
            if "context" in sig.parameters:
                func_kwargs["context"] = context
            
            # 执行函数
            if self._is_async:
                result = await self._func(**func_kwargs)
            else:
                # 在事件循环中运行同步函数
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: self._func(**func_kwargs))
            
            # 格式化结果
            formatted_data = self._format_result(result)
            
            return ToolResult(
                tool_name=self._name,
                success=True,
                data=result,
                formatted_data=formatted_data,
                parameters=parameters
            )
        
        except Exception as e:
            return ToolResult(
                tool_name=self._name,
                success=False,
                data=None,
                error=str(e),
                parameters=parameters
            )
    
    def _format_result(self, result: Any) -> str:
        """
        格式化工具返回结果（初步处理）
        
        Args:
            result: 原始结果
        
        Returns:
            格式化后的字符串
        """
        # 应用自定义格式化器
        if self._result_formatter:
            try:
                result = self._result_formatter(result)
            except Exception:
                # 如果格式化失败，使用原始结果
                pass
        
        # 转换为字符串
        result_str = str(result)
        
        # 截断过长结果
        if self._max_result_length and len(result_str) > self._max_result_length:
            result_str = result_str[:self._max_result_length] + "\n... (truncated)"
        
        return result_str
