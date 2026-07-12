"""
本地工具装饰器 - 将 Python 函数转换为工具
"""
import inspect
from typing import Callable, Optional, Dict, Any, List, get_type_hints
from .local_tool import LocalTool


def _type_to_schema(pytype):
    """
    将 Python 类型注解映射为简单 JSON schema 类型
    
    Args:
        pytype: Python 类型
    
    Returns:
        JSON Schema 类型字符串
    """
    import sys
    
    typemap = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    
    # 兼容 typing 的范型
    origin = None
    if sys.version_info >= (3, 10):
        import types
        if isinstance(pytype, types.GenericAlias):
            origin = pytype.__origin__
    
    # 处理 typing 模块的泛型
    if hasattr(pytype, '__origin__'):
        origin = pytype.__origin__
    
    if origin is not None:
        return typemap.get(origin, "string")
    
    return typemap.get(pytype, "string")


def _infer_schema_fragment(pytype) -> Dict[str, Any]:
    """
    推导单个参数的 JSON Schema 片段。
    """
    origin = getattr(pytype, "__origin__", None)
    args = getattr(pytype, "__args__", ())

    if origin is list:
        item_type = "string"
        if args:
            item_type = _type_to_schema(args[0])
        return {
            "type": "array",
            "items": {"type": item_type},
        }

    return {"type": _type_to_schema(pytype)}


def _infer_parameters_from_signature(fn: Callable) -> List[Dict[str, Any]]:
    """
    从函数签名获得参数 Schema 列表
    
    Args:
        fn: 函数对象
    
    Returns:
        参数 schema 列表
    """
    sig = inspect.signature(fn)
    try:
        type_hints = get_type_hints(fn)
    except Exception:
        # 如果无法获取类型提示，使用空字典
        type_hints = {}
    
    params = []
    for name, param in sig.parameters.items():
        if name == "context":
            continue  # ToolContext 类型单独约定，不算 Tool 参数schema

        param_type = type_hints.get(name, str)  # 默认当做 str
        schema_fragment = _infer_schema_fragment(param_type)

        param_schema = {"name": name, "required": param.default is inspect.Parameter.empty}
        param_schema.update(schema_fragment)
        
        if param.annotation is not inspect.Parameter.empty:
            param_schema["annotation"] = str(param.annotation)
        
        if param.default is not inspect.Parameter.empty:
            param_schema["default"] = param.default
        
        params.append(param_schema)
    
    return params


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[List[Dict[str, Any]]] = None,
    result_formatter: Optional[Callable[[Any], str]] = None,
    max_result_length: Optional[int] = None
):
    """
    本地工具装饰器
    
    Args:
        name: 工具名称（默认使用函数名）
        description: 工具描述（必填）
        parameters: 参数 schema 列表，若未填写则自动推导自函数签名和类型注解
        result_formatter: 结果格式化函数（可选）
        max_result_length: 结果最大长度限制（超出会截断）
    
    Returns:
        装饰器函数
    
    Example:
        @tool(
            description="搜索相关文档",
            max_result_length=5000
        )
        async def search_documents(query: str, limit: int = 10, context: ToolContext = None):
            # 实现搜索逻辑
            results = perform_search(query, limit)
            
            # 可以使用 context 共享状态
            if context:
                context.set("last_search_query", query)
            
            return results
    """
    def decorator(func: Callable) -> LocalTool:
        arg_schema = parameters or _infer_parameters_from_signature(func)
        return LocalTool(
            func=func,
            name=name or func.__name__,
            description=description or "",
            parameters=arg_schema,
            result_formatter=result_formatter,
            max_result_length=max_result_length
        )
    
    return decorator
