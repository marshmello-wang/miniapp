# User Interface 协议

Agent 框架的输入输出协议，定义了如何向 Agent 提交任务以及如何接收执行结果。

---

## 输入：TaskInput

### 基本结构

```python
from agent_framework.user_interface import TaskInput, Message, MessageContent

task = TaskInput(
    session_id="session-001",  # 会话 ID，同一 session 下的多个 task 可复用 KV cache
    task_id="task-001",        # 任务 ID
    messages=[...],            # 消息列表
    context={...},             # 可选的额外上下文
    config=AgentConfig(...)    # 可选的配置
)
```

**说明：**
- `session_id`：会话级别的标识，同一 session 下的多个 task 可以共享推理状态（如 KV cache）
- `task_id`：任务级别的标识，每个任务唯一

### 创建消息

**纯文本消息：**

```python
msg = Message.from_role_and_text("user", "帮我计算 2+2")
```

**带图片的消息：**

```python
from agent_framework.user_interface import ImageContent

msg = Message.from_role_and_content(
    role="user",
    content=[
        MessageContent.from_text("这张图是什么？"),
        MessageContent.from_image(ImageContent.from_path("photo.jpg"))
    ]
)
```

**图片支持两种方式：**

```python
# 方式 1: 文件路径
img = ImageContent.from_path("/path/to/image.jpg")

# 方式 2: Base64 编码
img = ImageContent.from_base64(base64_str, mime_type="image/jpeg")
```

---

## 输出：Event 流

Agent 通过 `Iterator[Event]` 返回执行过程，每个 Event 包含：

```python
@dataclass
class Event:
    event_id: str         # 事件 ID
    session_id: str       # 会话 ID
    task_id: str          # 任务 ID
    event_type: str       # 事件类型（由 Agent Loop 自定义）
    content: List[ContentBlock]  # 内容块列表
    timestamp: float      # 时间戳
    metadata: Optional[Dict[str, Any]]  # 可选的元数据
```

### 内容块类型

**TextBlock** - 文本内容：

```python
TextBlock(text="我正在思考...")
```

**ImageBlock** - 图片内容：

```python
ImageBlock(
    image=ImageContent.from_path("result.png"),
    caption="生成的图表"
)
```

**ToolCallBlock** - 工具调用：

```python
ToolCallBlock(
    tool_name="search_web",
    tool_input={"query": "Python"},
    call_id="call-001"
)
```

**ToolResultBlock** - 工具结果：

```python
ToolResultBlock(
    tool_name="search_web",
    result={"items": [...]},
    call_id="call-001",
    is_error=False
)
```

**StructuredDataBlock** - 结构化数据：

```python
StructuredDataBlock(
    data={"plan": ["step1", "step2"]},
    schema_name="planning_result"
)
```

---

## 使用示例

### 提交任务并处理事件流

```python
from agent_framework.user_interface import (
    TaskInput, Message, TextBlock, ToolCallBlock
)

# 1. 创建任务
task = TaskInput(
    session_id="session-001",
    task_id="task-001",
    messages=[Message.from_role_and_text("user", "搜索 Python 教程")]
)

# 2. 执行 Agent
for event in agent.run(task):
    print(f"[{event.event_type}]")
    
    # 3. 处理内容块
    for block in event.content:
        if isinstance(block, TextBlock):
            print(f"  文本: {block.text}")
        elif isinstance(block, ToolCallBlock):
            print(f"  调用工具: {block.tool_name}")
        elif isinstance(block, ToolResultBlock):
            print(f"  结果: {block.result}")
```

### 实现一个简单的 Agent

```python
from typing import Iterator
from agent_framework.user_interface import Agent, TaskInput, Event, TextBlock

class SimpleAgent:
    def run(self, task_input: TaskInput) -> Iterator[Event]:
        # 发送事件
        yield Event(
            event_id="evt-1",
            session_id=task_input.session_id,
            task_id=task_input.task_id,
            event_type="thinking",  # 自定义事件类型
            content=[TextBlock("正在处理...")]
        )
        
        # ... 执行逻辑 ...
        
        yield Event(
            event_id="evt-2",
            session_id=task_input.session_id,
            task_id=task_input.task_id,
            event_type="complete",
            content=[TextBlock("完成")]
        )
```

---

## 说明

- `event_type` 由具体的 Agent Loop 自定义（如 ReAct 可能使用 "reasoning"、"action"、"observation"）
- 工具结果在 `ToolResultBlock` 中完整返回
- 图片支持 base64 和文件路径两种方式
- 所有类型都有完整的 Python typing 支持
