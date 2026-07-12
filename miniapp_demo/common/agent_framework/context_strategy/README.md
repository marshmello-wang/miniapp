# Context Strategy 模块

上下文策略模块，是 agent 框架的核心业务逻辑模块。负责将用户输入、执行轨迹、环境状态转换为模型可用的上下文。

## 模块职责

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│ TaskInput   │────▶│             │     │                  │
└─────────────┘     │   Context   │────▶│  ModelContext    │
┌─────────────┐     │   Builder   │     │                  │
│ Events      │────▶│             │     └──────────────────┘
└─────────────┘     │  (stateful) │
┌─────────────┐     │             │
│ Environment │────▶│             │
│ States      │     └─────────────┘
└─────────────┘            │
                           ▼
                  ┌─────────────────┐
                  │ ContextStrategy │ (可替换)
                  │ + Truncation    │
                  └─────────────────┘
```

## 文件结构

```
context_strategy/
├── __init__.py           # 模块导出
├── protocol.py           # 核心协议接口和数据结构
├── truncation.py         # 截断策略
├── builder.py            # 有状态的上下文构建器
├── default_strategy.py   # 默认实现示例
└── README.md             # 本文档
```

## 核心概念

### 1. EnvironmentState（环境状态）

表示在上下文中唯一且需要持续更新的状态信息，如容器状态、产物状态等。

```python
from context_strategy.protocol import EnvironmentState

# 创建容器状态
container_state = EnvironmentState(
    key="container_status",
    content="Container ID: abc123\nStatus: Running\nPorts: 8080:80",
    position="system",  # 拼接到 system prompt
    priority=10         # 同位置下的排序优先级
)
```

**position 选项：**
- `"system"`: 拼接到 system prompt 末尾
- `"user_prefix"`: 作为最新 user message 的前缀
- `"assistant_suffix"`: 作为最新 assistant message 的后缀

### 2. ContextStrategy（上下文策略协议）

定义上下文构建的核心接口，不同 agent 实现自己的策略。

```python
from context_strategy.protocol import ContextStrategy

class MyAgentStrategy:
    """自定义上下文策略"""
    
    def build_context(
        self,
        task_input: TaskInput,
        events: List[Event],
        environment_states: Dict[str, EnvironmentState],
        system_prompt: str,
        tools: Optional[List[ToolSchema]] = None
    ) -> ModelContext:
        # 自定义上下文构建逻辑
        ...
        return model_context
```

### 3. TruncationStrategy（截断策略）

控制上下文长度，避免超出模型 token 限制。

```python
from context_strategy.truncation import (
    NoTruncation,              # 不截断
    SlidingWindowTruncation,   # 滑动窗口
    MessageCountTruncation,    # 消息数量限制
    TokenEstimateTruncation,   # Token 估算截断
    CompositeTruncation        # 组合策略
)

# 滑动窗口：保留最近 10 轮对话
truncation = SlidingWindowTruncation(max_turns=10, keep_first=True)

# 组合策略：先按 token 截断，再按轮数截断
truncation = CompositeTruncation([
    TokenEstimateTruncation(max_tokens=8000),
    SlidingWindowTruncation(max_turns=20)
])
```

### 4. ContextBuilder（上下文构建器）

在 task 维度内保持状态的构建器，是使用 context_strategy 的主要入口。

```python
from context_strategy.builder import ContextBuilder
from context_strategy.default_strategy import DefaultContextStrategy

# 创建构建器
builder = ContextBuilder(
    strategy=DefaultContextStrategy(),
    base_system_prompt="You are a helpful coding assistant.",
    truncation=SlidingWindowTruncation(max_turns=15),
    tools=[tool1, tool2]
)
```

## 使用示例

### 基础用法

```python
from context_strategy.builder import ContextBuilder
from context_strategy.default_strategy import DefaultContextStrategy
from context_strategy.truncation import SlidingWindowTruncation
from context_strategy.protocol import EnvironmentState

# 1. 创建构建器
builder = ContextBuilder(
    strategy=DefaultContextStrategy(),
    base_system_prompt="You are a helpful assistant.",
    truncation=SlidingWindowTruncation(max_turns=10)
)

# 2. 开始新任务
builder.reset(task_input)

# 3. 在 react loop 中使用
# 添加执行事件
builder.add_event(reasoning_event)
builder.add_event(tool_call_event)

# 更新环境状态
builder.update_environment("container", EnvironmentState(
    key="container",
    content="Status: Running",
    position="system"
))

# 构建上下文
context = builder.build()

# 4. 调用模型
response = await model_proxy.complete(context, config)

# 5. 继续循环
builder.add_event(tool_result_event)
context = builder.build()
```

### 动态修改 System Prompt

```python
# 添加技能描述
builder.modify_system_prompt(
    lambda p: p + "\n\n## Available Skills\n- Web Search\n- Code Execution"
)

# 重置到基础 prompt
builder.reset_system_prompt()
```

### 自定义上下文策略

```python
from context_strategy.protocol import ContextStrategy, EnvironmentState
from model_proxy.context import ModelContext, ChatMessage

class CodeAgentStrategy:
    """代码助手的上下文策略"""
    
    def build_context(
        self,
        task_input,
        events,
        environment_states,
        system_prompt,
        tools=None
    ) -> ModelContext:
        messages = []
        
        # 1. 添加代码上下文（从环境状态）
        code_context = environment_states.get("code_context")
        if code_context:
            # 特殊处理代码上下文
            ...
        
        # 2. 处理用户消息
        for msg in task_input.messages:
            # 自定义转换逻辑
            ...
        
        # 3. 处理执行轨迹
        for event in events:
            # 自定义事件处理
            ...
        
        return ModelContext(
            messages=messages,
            session_id=task_input.session_id,
            system_prompt=system_prompt,
            tools=tools
        )
```

## 截断策略详解

### SlidingWindowTruncation

保留最近 N 轮对话（一轮 = user + assistant）。

```python
truncation = SlidingWindowTruncation(
    max_turns=10,      # 最大轮数
    keep_first=True    # 是否保留第一条消息（任务描述）
)
```

### MessageCountTruncation

简单地保留最近 N 条消息。

```python
truncation = MessageCountTruncation(
    max_messages=20,   # 最大消息数
    keep_first=True    # 是否保留第一条消息
)
```

### TokenEstimateTruncation

基于字符数估算 token，截断超出限制的消息。

```python
truncation = TokenEstimateTruncation(
    max_tokens=4000,       # 最大 token 数
    chars_per_token=3.0,   # 每 token 平均字符数（中英混合）
    keep_first=True
)
```

### CompositeTruncation

组合多个策略，按顺序执行。

```python
truncation = CompositeTruncation([
    TokenEstimateTruncation(max_tokens=8000),
    SlidingWindowTruncation(max_turns=20)
])
```

## 设计原则

1. **ContextStrategy 为纯函数式接口**：无状态，方便测试和复用
2. **ContextBuilder 维护状态**：在 task 维度累积 events 和 environment
3. **Truncation 独立抽象**：可组合使用，不耦合具体策略
4. **Environment States 按 key 去重**：同 key 的状态会被覆盖更新
5. **System Prompt 支持动态修改**：通过 modifier 函数链式修改

## 与其他模块的关系

- **user_interface**: 提供 `TaskInput` 和 `Event` 作为输入
- **tool_adapter**: 提供 `ToolSchema` 和 `ToolResult`
- **model_proxy**: 输出 `ModelContext` 用于模型调用

