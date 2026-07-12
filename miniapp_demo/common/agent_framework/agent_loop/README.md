# Agent Loop 模块

Agent Loop 模块提供了 Agent 执行循环的实现，是整个框架的核心串联层。

## 概述

Agent Loop 负责将以下模块串联起来：
- **User Interface**: 接收任务输入，输出事件流
- **Model Proxy**: 调用大语言模型
- **Tool Adapter**: 执行工具调用
- **Context Strategy**: 构建模型调用上下文

目前支持 **React 模式**（Reasoning-Action 循环）。

## 核心组件

### ReactAgent

React Agent 实现了经典的 Reasoning-Action 循环模式：

1. 调用模型进行推理（Reasoning）
2. 解析模型响应，判断是否需要执行工具
3. 如果需要，执行工具（Action）并获取结果
4. 将工具结果加入上下文，继续下一轮推理
5. 直到模型返回 stop 或达到最大迭代次数

```python
from agent_loop import create_react_agent, ReactAgentConfig
from model_proxy import OpenAIProxy, ModelConfig
from tool_adapter import ToolRegistry
from context_strategy import DefaultStrategy
from user_interface import TaskInput, Message

# 1. 准备配置
config = ReactAgentConfig(
    model_proxy=OpenAIProxy(api_key="your-api-key"),
    model_config=ModelConfig(model="gpt-4o"),
    tool_registry=ToolRegistry(),
    context_strategy=DefaultStrategy(),
    system_prompt="You are a helpful assistant.",
    max_iterations=20  # 防止死循环
)

# 2. 创建 Agent
agent = create_react_agent(config)

# 3. 准备任务输入
task = TaskInput(
    session_id="session-1",
    task_id="task-1",
    messages=[Message.from_role_and_text("user", "What is 2 + 2?")]
)

# 4. 执行并处理事件流
for event in agent.run(task):
    print(f"[{event.event_type}]")
    for block in event.content:
        if hasattr(block, 'text'):
            print(block.text)
```

### ReactAgentConfig

配置类，包含所有必要的依赖和参数：

| 参数 | 类型 | 描述 |
|------|------|------|
| `model_proxy` | `ModelProxy` | 模型代理实例 |
| `model_config` | `ModelConfig` | 模型调用配置 |
| `tool_registry` | `ToolRegistry` | 工具注册中心 |
| `context_strategy` | `ContextStrategy` | 上下文构建策略 |
| `system_prompt` | `str` | 基础 system prompt |
| `max_iterations` | `int` | 最大迭代次数（默认 20）|
| `truncation_strategy` | `TruncationStrategy` | 截断策略（可选）|
| `hooks` | `List[Hook]` | 干预钩子列表（可选）|

## 干预接口（Hooks）

Hook 机制允许在执行的关键节点进行干预，支持：
- 监控执行过程
- 注入额外指令
- 修改工具参数
- 强制停止或跳过某些阶段

### Hook 触发点

| 阶段 | 触发时机 | 可用操作 |
|------|----------|----------|
| `before_reasoning` | 每次调用模型前 | 跳过推理、注入 prompt、强制停止 |
| `after_reasoning` | 模型返回后 | 强制停止 |
| `before_tool_execution` | 执行工具前 | 跳过执行、修改参数、强制停止 |
| `after_tool_execution` | 工具执行后 | 强制停止 |

### HookContext

传递给 Hook 的上下文信息：

```python
@dataclass
class HookContext:
    phase: str              # 当前阶段
    iteration: int          # 当前迭代次数
    task_input: TaskInput   # 原始任务输入
    events: List[Event]     # 已产生的事件列表
    current_response: Optional[ModelResponse]  # 当前模型响应
    current_tool_name: Optional[str]           # 当前工具名称
    current_tool_result: Optional[ToolResult]  # 当前工具结果
    extra_data: Dict[str, Any]  # 扩展数据
```

### HookResult

Hook 返回的干预指令：

```python
@dataclass
class HookResult:
    skip_phase: bool = False              # 跳过当前阶段
    inject_prompt: Optional[str] = None   # 注入额外 prompt
    force_stop: bool = False              # 强制停止循环
    modify_tool_params: Optional[Dict] = None  # 修改工具参数
    extra_data: Dict[str, Any] = {}       # 扩展数据
```

### 示例：实现日志 Hook

```python
from agent_loop import Hook, HookContext, HookResult, DefaultHook

class LoggingHook(DefaultHook):
    """记录执行过程的 Hook"""
    
    def before_reasoning(self, ctx: HookContext) -> HookResult:
        print(f"[Iteration {ctx.iteration}] Starting reasoning...")
        return HookResult()
    
    def after_reasoning(self, ctx: HookContext) -> HookResult:
        if ctx.current_response:
            text = ctx.current_response.get_text()
            print(f"[Iteration {ctx.iteration}] Model output: {text[:100]}...")
        return HookResult()
    
    def before_tool_execution(self, ctx: HookContext) -> HookResult:
        print(f"[Iteration {ctx.iteration}] Executing tool: {ctx.current_tool_name}")
        return HookResult()
    
    def after_tool_execution(self, ctx: HookContext) -> HookResult:
        if ctx.current_tool_result:
            print(f"[Iteration {ctx.iteration}] Tool result: success={ctx.current_tool_result.success}")
        return HookResult()

# 使用 Hook
config = ReactAgentConfig(
    ...,
    hooks=[LoggingHook()]
)
```

### 示例：实现迭代限制 Hook

```python
class IterationLimitHook(DefaultHook):
    """在特定条件下强制停止的 Hook"""
    
    def __init__(self, max_tool_calls: int = 10):
        self.max_tool_calls = max_tool_calls
        self.tool_call_count = 0
    
    def before_tool_execution(self, ctx: HookContext) -> HookResult:
        self.tool_call_count += 1
        if self.tool_call_count > self.max_tool_calls:
            print(f"Reached max tool calls ({self.max_tool_calls}), stopping...")
            return HookResult.stop()
        return HookResult()
```

### 组合多个 Hook

使用 `CompositeHook` 组合多个 Hook：

```python
from agent_loop import CompositeHook

hooks = CompositeHook([
    LoggingHook(),
    IterationLimitHook(max_tool_calls=5),
])

config = ReactAgentConfig(
    ...,
    hooks=[hooks]  # 或者直接传递列表：hooks=[LoggingHook(), IterationLimitHook()]
)
```

## 事件类型

ReactAgent 会产生以下事件类型：

| 事件类型 | 描述 | 内容块类型 |
|----------|------|------------|
| `reasoning` | 模型推理输出 | `TextBlock`, `ToolCallBlock` |
| `tool_result` | 工具执行结果 | `ToolResultBlock` |
| `task_complete` | 任务完成 | 空或 `TextBlock` |
| `warning` | 警告信息 | `TextBlock` |
| `error` | 错误信息 | `TextBlock` |

## 异步支持

除了同步的 `run()` 方法，ReactAgent 也提供异步的 `run_async()` 方法：

```python
import asyncio

async def main():
    agent = create_react_agent(config)
    
    async for event in agent.run_async(task_input):
        print(f"Event: {event.event_type}")

asyncio.run(main())
```

## 设计原则

1. **事件驱动**: 所有输出都通过事件流上报，支持实时展示
2. **可扩展**: 通过 Hook 机制支持各种干预和扩展
3. **异步优先**: 内部使用异步实现，同时提供同步接口
4. **无状态**: Agent 本身无状态，状态通过 ContextBuilder 管理

