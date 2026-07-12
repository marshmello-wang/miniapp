# agent_framework

`agent_framework` 是一套可组合的 Agent 基础设施，包含：
- 输入输出协议（`user_interface`）
- 工具抽象与执行（`tool_adapter`）
- 上下文构建策略（`context_strategy`）
- ReAct 执行循环（`agent_loop`）

## 子目录说明

- `agent_loop/`
  - Agent 主执行循环实现，目前核心是 `ReactAgent`。
  - 负责：模型调用、解析 tool calls、执行工具、产出事件流、迭代终止控制（`max_iterations`）。

- `tool_adapter/`
  - 工具层抽象与适配。
  - 负责：`Tool` 协议、`@tool` 装饰器、`ToolRegistry` 注册中心、`ToolExecutor` 执行器、`ToolContext` 上下文共享、MCP 工具包装。

- `user_interface/`
  - Agent 的统一输入输出协议层。
  - 输入：`TaskInput / Message / MessageContent / ImageContent`
  - 输出：`Event + ContentBlock`（如 `TextBlock`、`ToolCallBlock`、`ToolResultBlock`）。

- `context_strategy/`
  - 将 `TaskInput + 历史 Event + tools schema + system prompt` 组装为模型可消费的 `ChatRequest`。
  - 提供默认实现 `DefaultContextStrategy` 与多种截断策略。

- `tests/`
  - 覆盖 `tool_adapter` 与 `user_interface` 的单测/集成测试。
  - 可以作为 usage 的“可执行文档”参考。

## Usage（参考 tests）

下面示例按 `tests/test_tool_adapter.py`、`tests/test_user_interface.py` 的模式整理，重点是工具集成、输入输出格式和 Agent 配置。

### 1) 集成 tools

```python
from common.agent_framework.tool_adapter import tool, ToolRegistry, ToolExecutor, ToolContext

@tool(description="Add two numbers")
async def add(a: int, b: int):
    return a + b

@tool(description="Record a message")
async def log_message(message: str, context: ToolContext = None):
    if context:
        logs = context.get("logs", [])
        logs.append(message)
        context.set("logs", logs)
    return f"Logged: {message}"

registry = ToolRegistry()
registry.register(add)
registry.register(log_message)

# 传给模型的 tools schema
tools_schema = registry.get_tools_schema()

executor = ToolExecutor(registry)
ctx = ToolContext(session_id="session-001")

result = await executor.execute("add", {"a": 3, "b": 5}, context=ctx, call_id="call-1")
assert result.success is True
assert result.data == 8
assert result.call_id == "call-1"
```

工具参数 schema 两种方式：
- 自动推导：从函数签名 + 类型注解推导（tests 已覆盖）
- 显式声明：在 `@tool(parameters=[...])` 中手工定义

### 2) 输入格式（TaskInput）

```python
from common.agent_framework.user_interface import (
    TaskInput, Message, MessageContent, ImageContent, AgentConfig
)

task_input = TaskInput(
    session_id="session-001",
    task_id="task-001",
    messages=[
        Message.from_role_and_text("user", "帮我计算 12 * 7"),
        Message.from_role_and_content("user", [
            MessageContent.from_text("并看下这张图"),
            MessageContent.from_image(ImageContent.from_path("/tmp/demo.png"))
        ])
    ],
    context={"project": "forge_os"},
    config=AgentConfig(
        model="gpt-4o",
        temperature=0.3,
        max_tokens=2048,
        extra_params={}
    )
)
```

`TaskInput` 关键字段：
- `session_id`: 会话标识（跨 task 复用上下文/缓存场景）
- `task_id`: 当前任务唯一标识
- `messages`: 用户/系统/助手消息列表（支持文本和图片）
- `context`: 可选结构化上下文
- `config`: 可选的输入侧配置（`AgentConfig`）

### 3) 输出格式（Event 流）

`ReactAgent.run(task_input)` 返回 `Iterator[Event]`。每个 `Event` 结构：
- `event_id`, `session_id`, `task_id`, `event_type`, `content`, `timestamp`, `metadata`

常见 `event_type`（来自 `ReactAgent`）：
- `reasoning`: 模型本轮推理结果（文本/思考/tool_call）
- `tool_result`: 工具执行结果
- `warning`: 如达到 `max_tokens` 截断
- `error`: 模型调用失败
- `task_complete`: 任务结束

常见 `content block`：
- `TextBlock(text=...)`
- `ThinkingBlock(thinking=...)`
- `ToolCallBlock(tool_name, tool_input, call_id)`
- `ToolResultBlock(tool_name, result, call_id, is_error, error_message)`

示例消费事件：

```python
from common.agent_framework.user_interface import TextBlock, ToolCallBlock, ToolResultBlock

for event in agent.run(task_input):
    print(event.event_type, event.metadata)
    for block in event.content:
        if isinstance(block, TextBlock):
            print("text:", block.text)
        elif isinstance(block, ToolCallBlock):
            print("tool_call:", block.tool_name, block.tool_input)
        elif isinstance(block, ToolResultBlock):
            print("tool_result:", block.result, "error?", block.is_error)
```

### 4) Agent 配置项（ReactAgentConfig）

`common.agent_framework.agent_loop.config.ReactAgentConfig`：

- `llm_client`: `LLMClient` 实例（必填）
- `tool_registry`: `ToolRegistry`（必填）
- `context_strategy`: `ContextStrategy`（必填，常用 `DefaultContextStrategy`）
- `system_prompt`: 基础系统提示词（必填，不能为空）
- `max_iterations`: 最大循环轮次，默认 `20`
- `max_tokens`: 模型单次最大 token，默认 `4096`
- `temperature`: 采样温度，默认 `1.0`
- `truncation_strategy`: 截断策略，可选
- `hooks`: Hook 列表，可选

最小可运行示例：

```python
from common.llm import LLMClient, LLMConfig
from common.agent_framework.agent_loop import ReactAgent, ReactAgentConfig
from common.agent_framework.context_strategy import DefaultContextStrategy
from common.agent_framework.tool_adapter import ToolRegistry

llm_client = LLMClient(LLMConfig(
    provider="gemini",
    api_key="YOUR_API_KEY",
    model="gemini-3-flash-preview"
))

registry = ToolRegistry()
# registry.register(...)

config = ReactAgentConfig(
    llm_client=llm_client,
    tool_registry=registry,
    context_strategy=DefaultContextStrategy(),
    system_prompt="You are a helpful assistant.",
    max_iterations=10,
    max_tokens=4096,
    temperature=0.7,
)

agent = ReactAgent(config)
```

## 建议阅读顺序

1. `tests/test_tool_adapter.py`：先看工具定义、schema、执行链路。
2. `tests/test_user_interface.py`：再看输入输出数据结构。
3. `user_interface/example.py`：最后看 ReactAgent 的端到端接入示例。
