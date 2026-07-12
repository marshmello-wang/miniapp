# Tool Adapter - 工具适配器

工具适配器模块提供统一的工具接口，支持本地 Python 函数和 MCP 工具的集成。

## 核心概念

### 1. Tool Protocol

所有工具（无论是本地函数还是 MCP 工具）都实现统一的 `Tool` 协议接口：

```python
class Tool(Protocol):
    @property
    def name(self) -> str: ...
    
    @property
    def description(self) -> str: ...
    
    @property
    def schema(self) -> ToolSchema: ...
    
    async def execute(
        self, 
        parameters: Dict[str, Any],
        context: Optional[ToolContext] = None
    ) -> ToolResult: ...
```

### 2. Tool Context

`ToolContext` 用于在工具间共享状态，支持工具链式调用。

**session_id**: 会话 ID，用于沙盒绑定、资源隔离等场景

```python
# 创建带 session_id 的上下文
context = ToolContext(session_id="session-001")

# 存取数据
context.set("key", "value")
value = context.get("key")
```

### 3. Tool Result

工具执行结果包含原始数据和格式化数据：

```python
@dataclass
class ToolResult:
    tool_name: str
    success: bool
    data: Any
    formatted_data: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    parameters: Optional[Dict[str, Any]] = None
    call_id: Optional[str] = None
```

## 使用指南

### 本地工具开发

#### 方式 1: 使用装饰器（推荐）

```python
from agent_framework.tool_adapter import tool, ToolContext

@tool(
    description="读取文件内容",
    parameters=[
        {"name": "file_path", "type": "string", "description": "文件路径", "required": True}
    ],
    max_result_length=10000
)
async def read_file(file_path: str, context: ToolContext = None):
    """读取文件内容"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 可选：在 context 中记录状态
    if context:
        context.set("last_file_read", file_path)
    
    return content
```

#### 方式 2: 自动推导参数（基于类型注解）

```python
@tool(description="搜索文件")
async def search_files(query: str, limit: int = 10, context: ToolContext = None):
    """
    搜索文件
    
    参数会自动从函数签名推导：
    - query: str (必需)
    - limit: int = 10 (可选，默认值 10)
    """
    # 实现搜索逻辑
    results = perform_search(query, limit)
    return results
```

#### 方式 3: 自定义结果格式化

```python
@tool(
    description="搜索代码库",
    result_formatter=lambda results: "\n".join([
        f"{r['file']}:{r['line']}" for r in results[:10]
    ]),
    max_result_length=5000
)
async def search_code(query: str, file_type: str = None, context: ToolContext = None):
    results = perform_code_search(query, file_type)
    
    if context:
        context.set("search_count", len(results))
    
    return results
```

### 工具注册和执行

```python
from agent_framework.tool_adapter import ToolRegistry, ToolExecutor, ToolContext

# 1. 创建注册中心和执行器
registry = ToolRegistry()
executor = ToolExecutor(registry)

# 2. 注册工具
registry.register(read_file)
registry.register(search_files)
registry.register(search_code)

# 3. 创建执行上下文
context = ToolContext()

# 4. 执行工具
result = await executor.execute(
    tool_name="read_file",
    parameters={"file_path": "/path/to/file.txt"},
    context=context
)

if result.success:
    print(f"Result: {result.formatted_data}")
else:
    print(f"Error: {result.error}")

# 5. 获取所有工具的 schema（用于传给模型）
tools_schema = registry.get_tools_schema()
```

### MCP 工具集成

#### 连接远程 MCP 服务器

```python
from agent_framework.tool_adapter import MCPToolAdapter

mcp_adapter = MCPToolAdapter()

# 连接远程服务器
await mcp_adapter.connect_remote_server(
    server_url="https://mcp-server.example.com",
    auth_token="your-token",
    namespace="remote"
)

# 获取 MCP 工具
mcp_tools = mcp_adapter.get_tools()

# 注册到工具注册中心
for tool in mcp_tools:
    registry.register(tool)
```

#### 启动本地 MCP 服务器

```python
# 启动本地文件系统 MCP 服务器
await mcp_adapter.start_local_server(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
    namespace="fs"
)

# 获取并注册工具
for tool in mcp_adapter.get_tools("fs"):
    registry.register(tool)

# 执行 MCP 工具（使用命名空间前缀）
result = await executor.execute(
    tool_name="fs:read_file",
    parameters={"path": "/workspace/README.md"},
    context=context
)
```

### 工具间状态共享

```python
# 工具 1: 搜索文件
@tool(description="搜索文件")
async def search_files(query: str, context: ToolContext = None):
    results = perform_search(query)
    
    if context:
        context.set("search_results", results)
        context.set("search_query", query)
    
    return results

# 工具 2: 分析搜索结果
@tool(description="分析搜索结果")
async def analyze_results(context: ToolContext = None):
    if not context:
        return "No context available"
    
    results = context.get("search_results", [])
    query = context.get("search_query", "unknown")
    
    return f"Found {len(results)} files for query: {query}"

# 执行工具链
context = ToolContext()
result1 = await executor.execute("search_files", {"query": "test"}, context)
result2 = await executor.execute("analyze_results", {}, context)
```

## 完整示例

```python
from agent_framework.tool_adapter import (
    tool, ToolRegistry, ToolExecutor, ToolContext, MCPToolAdapter
)

# 定义本地工具
@tool(
    description="读取文件内容",
    max_result_length=5000
)
async def read_file(path: str, context: ToolContext = None):
    with open(path, 'r') as f:
        return f.read()

@tool(description="列出目录")
async def list_directory(directory: str, context: ToolContext = None):
    import os
    return os.listdir(directory)

# 初始化
registry = ToolRegistry()
executor = ToolExecutor(registry)

# 注册本地工具
registry.register(read_file)
registry.register(list_directory)

# 集成 MCP 工具（可选）
# mcp_adapter = MCPToolAdapter()
# await mcp_adapter.start_local_server(...)
# for tool in mcp_adapter.get_tools():
#     registry.register(tool)

# 创建上下文并执行
context = ToolContext()

result1 = await executor.execute(
    "list_directory",
    {"directory": "/workspace"},
    context
)

result2 = await executor.execute(
    "read_file",
    {"path": "/workspace/README.md"},
    context
)

# 获取工具 schema
tools_schema = registry.get_tools_schema()
print(f"Available tools: {[s['name'] for s in tools_schema]}")
```

## 注意事项

1. **异步函数**: 工具函数应该是异步的（使用 `async def`），如果是同步函数也会自动处理
2. **Context 参数**: 如果函数签名包含 `context: ToolContext` 参数，执行时会自动传入
3. **参数推导**: 可以手动指定参数 schema，也可以通过类型注解自动推导
4. **命名空间**: MCP 工具使用 `namespace:tool_name` 格式避免名称冲突
5. **结果格式化**: 支持自定义格式化函数和长度限制，适配不同场景

## MCP 集成说明

**注意**: MCP 工具的实际实现需要安装 MCP SDK：

```bash
pip install mcp
```

当前实现提供了 MCP 集成的框架，实际的连接和调用逻辑需要根据 MCP SDK 的具体 API 来完成。`mcp_adapter.py` 和 `mcp_tool.py` 中标记了 `TODO` 的部分需要在有实际 MCP SDK 文档后进行实现。

## API 参考

### 装饰器参数

- `name`: 工具名称（默认使用函数名）
- `description`: 工具描述（必填）
- `parameters`: 参数 schema 列表（可选，默认从函数签名推导）
- `result_formatter`: 结果格式化函数
- `max_result_length`: 结果最大长度限制

### ToolRegistry 方法

- `register(tool)`: 注册工具
- `unregister(tool_name)`: 注销工具
- `get(tool_name)`: 获取工具
- `list_tools()`: 列出所有工具
- `get_tools_schema()`: 获取所有工具的 schema
- `has_tool(tool_name)`: 检查工具是否存在
- `clear()`: 清空所有工具

### ToolExecutor 方法

- `execute(tool_name, parameters, context, call_id)`: 执行工具

### ToolContext 方法

- `set(key, value)`: 设置值
- `get(key, default)`: 获取值
- `update(data)`: 批量更新
- `has(key)`: 检查键是否存在
- `clear()`: 清空上下文
- `to_dict()`: 转换为字典


# Tool Adapter 快速参考指南

## 快速开始

### 1. 创建本地工具

```python
from agent_framework.tool_adapter import tool, ToolContext

@tool(description="你的工具描述")
async def your_tool(param1: str, param2: int = 10, context: ToolContext = None):
    """实现你的工具逻辑"""
    result = do_something(param1, param2)
    
    # 可选：在 context 中保存状态
    if context:
        context.set("key", "value")
    
    return result
```

### 2. 注册和执行工具

```python
from agent_framework.tool_adapter import ToolRegistry, ToolExecutor, ToolContext

# 初始化
registry = ToolRegistry()
executor = ToolExecutor(registry)

# 注册工具
registry.register(your_tool)

# 执行工具
context = ToolContext()
result = await executor.execute(
    tool_name="your_tool",
    parameters={"param1": "value", "param2": 20},
    context=context
)

if result.success:
    print(result.data)
else:
    print(result.error)
```

## 核心 API

### @tool 装饰器参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 工具名称（默认使用函数名） |
| `description` | `str` | 工具描述（必填） |
| `parameters` | `List[Dict]` | 参数 schema（可选，默认自动推导） |
| `result_formatter` | `Callable` | 结果格式化函数 |
| `max_result_length` | `int` | 结果最大长度 |

### 参数 Schema 格式

```python
parameters=[
    {
        "name": "参数名",
        "type": "类型",  # string, integer, number, boolean, array, object
        "description": "参数描述",
        "required": True/False,
        "default": 默认值  # 可选
    }
]
```

### ToolContext 方法

| 方法 | 说明 |
|------|------|
| `set(key, value)` | 设置值 |
| `get(key, default=None)` | 获取值 |
| `update(dict)` | 批量更新 |
| `has(key)` | 检查是否存在 |
| `clear()` | 清空 |
| `to_dict()` | 转换为字典 |

### ToolRegistry 方法

| 方法 | 说明 |
|------|------|
| `register(tool)` | 注册工具 |
| `unregister(name)` | 注销工具 |
| `get(name)` | 获取工具 |
| `list_tools()` | 列出所有工具 |
| `get_tools_schema()` | 获取工具 schema |
| `has_tool(name)` | 检查是否存在 |
| `clear()` | 清空 |

### ToolResult 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `tool_name` | `str` | 工具名称 |
| `success` | `bool` | 是否成功 |
| `data` | `Any` | 原始数据 |
| `formatted_data` | `str` | 格式化数据 |
| `error` | `str` | 错误信息 |
| `parameters` | `dict` | 调用参数 |
| `call_id` | `str` | 调用 ID |
| `metadata` | `dict` | 元数据 |

## 常见模式

### 模式 1: 基础工具

```python
@tool(description="读取文件")
async def read_file(path: str):
    with open(path) as f:
        return f.read()
```

### 模式 2: 带默认值的工具

```python
@tool(description="搜索")
async def search(query: str, limit: int = 10):
    return perform_search(query, limit)
```

### 模式 3: 使用上下文

```python
@tool(description="分析上次结果")
async def analyze(context: ToolContext = None):
    if not context:
        return "No context"
    data = context.get("last_result")
    return analyze_data(data)
```

### 模式 4: 自定义格式化

```python
@tool(
    description="搜索代码",
    result_formatter=lambda r: "\n".join(r[:5]),
    max_result_length=1000
)
async def search_code(query: str):
    return find_code(query)
```

### 模式 5: 手动指定 Schema

```python
@tool(
    description="复杂工具",
    parameters=[
        {"name": "config", "type": "object", "description": "配置", "required": True},
        {"name": "options", "type": "array", "description": "选项", "required": False}
    ]
)
async def complex_tool(config: dict, options: list = None):
    pass
```

## 与 User Interface 集成

```python
from agent_framework.user_interface import Event, ToolCallBlock, ToolResultBlock

def to_event(tool_result, task_id, event_id):
    return Event(
        event_id=event_id,
        task_id=task_id,
        event_type="tool_execution",
        content=[
            ToolCallBlock(
                tool_name=tool_result.tool_name,
                tool_input=tool_result.parameters,
                call_id=tool_result.call_id
            ),
            ToolResultBlock(
                tool_name=tool_result.tool_name,
                result=tool_result.data,
                call_id=tool_result.call_id,
                is_error=not tool_result.success,
                error_message=tool_result.error
            )
        ]
    )
```

## MCP 工具集成（待实现）

```python
from agent_framework.tool_adapter import MCPToolAdapter

mcp = MCPToolAdapter()

# 启动本地服务器
await mcp.start_local_server(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/path"],
    namespace="fs"
)

# 注册 MCP 工具
for tool in mcp.get_tools("fs"):
    registry.register(tool)

# 使用 MCP 工具（带命名空间前缀）
result = await executor.execute("fs:read_file", {"path": "/file.txt"})
```

## 注意事项

1. **异步优先**: 工具函数推荐使用 `async def`，同步函数也会被自动处理
2. **Context 参数**: 必须命名为 `context` 且类型为 `ToolContext`
3. **参数推导**: 基于类型注解，支持 `str`, `int`, `float`, `bool`, `list`, `dict`
4. **错误处理**: 工具内部异常会被自动捕获并返回 `ToolResult(success=False)`
5. **命名空间**: MCP 工具使用 `namespace:tool_name` 格式避免冲突

## 已知局限性

### 参数自动推导的局限性

当使用类型注解自动推导参数 schema 时，**不支持嵌套结构的详细定义**。

例如，对于以下函数：

```python
from typing import List
from dataclasses import dataclass

@dataclass
class Item:
    name: str   # 希望添加 description: "物品名称"
    value: int  # 希望添加 description: "物品价值"

@tool(description="处理物品列表")
async def process_items(items: List[Item]):
    pass
```

自动推导只会生成：

```json
{
  "name": "items",
  "type": "array"
}
```

而**不会**生成包含 Item 内部字段描述的完整 schema：

```json
{
  "name": "items",
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "name": {"type": "string", "description": "物品名称"},
      "value": {"type": "integer", "description": "物品价值"}
    }
  }
}
```

**解决方案**：对于需要嵌套结构描述的参数，请使用显式 `parameters` 定义：

```python
@tool(
    description="处理物品列表",
    parameters=[
        {
            "name": "items",
            "type": "array",
            "description": "物品列表",
            "required": True,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "物品名称"},
                    "value": {"type": "integer", "description": "物品价值"}
                },
                "required": ["name", "value"]
            }
        }
    ]
)
async def process_items(items: list):
    pass
```

## 调试技巧

```python
# 查看工具 schema
schema = registry.get(tool_name).schema.to_json_schema()
print(schema)

# 查看所有工具
for tool in registry.list_tools():
    print(f"{tool.name}: {tool.description}")

# 查看上下文状态
print(context.to_dict())

# 查看工具结果详情
print(f"Success: {result.success}")
print(f"Data: {result.data}")
print(f"Formatted: {result.formatted_data}")
print(f"Error: {result.error}")
```

## 完整示例

参考以下示例文件：
- `tool_adapter/example.py` - 基础使用示例
- `tool_adapter/integration_example.py` - 与 user_interface 集成示例
- `tool_adapter/README.md` - 详细文档

