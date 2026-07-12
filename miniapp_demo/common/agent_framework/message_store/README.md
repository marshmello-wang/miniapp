# MessageStore — Agent 消息存储系统

基于 SQLite 的轻量级消息持久化模块，为 agent framework 提供上游存储能力。

## 数据层次

```
User
├── UserMemory          # 跨 session 结构化记忆 (JSON + 版本号)
└── Session
    ├── metadata        # session 级 KV 存储 (JSON，按命名空间分区)
    └── Round 0..N      # 交互轮次
        ├── user_content    # 用户输入
        ├── ai_content      # AI 回复
        └── trajectory      # agent 执行轨迹
```

## 快速接入

```python
from common.agent_framework.message_store import MessageStore

store = MessageStore(db_path="my_agent.db")   # 自动建表

# 1. 创建用户和 session
sid = store.create_session("user_alice")       # 自动创建用户

# 2. 用户发送消息 → 开始新轮次
round_idx = store.start_round(sid, [
    {"type": "text", "content": "帮我搜索今天的天气"},
])

# 3. agent 执行完毕 → 写入回复和轨迹
store.complete_round(sid, round_idx,
    ai_content=[
        {"type": "text", "content": "今天北京晴，最高温度 32°C。"},
    ],
    trajectory=[
        {"event": "reasoning", "content": "用户想知道天气"},
        {"event": "tool_call", "name": "weather_api", "arguments": {"city": "北京"}},
        {"event": "tool_result", "content": "晴 32°C"},
        {"event": "response", "content": "今天北京晴，最高温度 32°C。"},
    ],
)

# 4. 读取历史
rounds = store.get_rounds(sid)
for r in rounds:
    print(f"Round {r.round_idx}: {r.user_content} → {r.ai_content}")

store.close()
```

## 核心 API

### MessageStore

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `__init__(db_path)` | 连接数据库，自动建表 | — |
| `close()` | 关闭连接 | — |

#### User

| 方法 | 说明 |
|------|------|
| `ensure_user(user_id)` | 确保用户存在（幂等） |
| `list_users()` | 返回所有 user_id 列表 |

#### Session

| 方法 | 说明 |
|------|------|
| `create_session(user_id, session_id=None)` | 创建 session，自动 `ensure_user`，返回 session_id |
| `list_sessions(user_id)` | 返回 `List[SessionInfo]`，按 updated_at 降序 |
| `get_session(session_id)` | 返回 `SessionInfo` 或 `None` |

#### Round（核心）

| 方法 | 说明 |
|------|------|
| `start_round(session_id, user_content)` | 创建新轮次，返回 `round_idx` |
| `complete_round(session_id, round_idx, ai_content, trajectory=None)` | 写入 AI 回复和执行轨迹 |
| `get_rounds(session_id)` | 返回 `List[Round]`，按 round_idx 升序 |
| `get_round(session_id, round_idx)` | 返回单个 `Round` 或 `None` |

#### Session Metadata KV

| 方法 | 说明 |
|------|------|
| `session_store_save(session_id, key, value, store_type="expire")` | 写入 KV（按 store_type 命名空间隔离） |
| `session_store_load(session_id, key)` | 读取 KV |
| `session_store_clear(session_id, store_type=None)` | 清除 KV（指定 store_type 或全部） |

#### User Memory（跨 Session）

| 方法 | 说明 |
|------|------|
| `get_user_memory(user_id)` | 返回 `UserMemory`（不存在则返回空默认值） |
| `set_user_memory(user_id, data, version=1)` | 写入/覆盖结构化记忆 |

## 数据模型

### Round

```python
@dataclass
class Round:
    round_idx: int
    user_content: List[dict]            # [{"type": "text|image|video", "content": "..."}]
    ai_content: Optional[List[dict]]    # 同格式，agent 未回复时为 None
    trajectory: Optional[List[dict]]    # Event.to_dict() 列表，完整执行轨迹
    created_at: float
    updated_at: float
```

### Content 格式

`user_content` 和 `ai_content` 使用统一的多模态格式：

```json
[
  {"type": "text",  "content": "你好"},
  {"type": "image", "content": "data:image/png;base64,..."},
  {"type": "video", "content": "https://example.com/video.mp4"}
]
```

### Trajectory 格式

`trajectory` 记录 agent loop 的完整事件流，每个事件是一个 dict：

```json
[
  {"event": "reasoning",    "content": "用户想查询天气"},
  {"event": "tool_call",    "name": "weather_api", "arguments": {"city": "北京"}},
  {"event": "tool_result",  "name": "weather_api", "content": "晴 32°C"},
  {"event": "response",     "content": "今天北京晴，最高温度 32°C。"}
]
```

具体的 event 字段由 agent loop 的 Event 类型定义，此处不做强约束。

### SessionInfo

```python
@dataclass
class SessionInfo:
    session_id: str
    user_id: str
    created_at: float
    updated_at: float
    metadata: Dict[str, Any]    # session 级 KV 存储
    round_count: int            # 轮次数
```

### UserMemory

```python
@dataclass
class UserMemory:
    user_id: str
    version: int                # 用于区分不同版本的解析方式
    data: Dict[str, Any]        # 结构化记忆 JSON
    updated_at: float
```

## 典型接入场景

### Agent Loop 接入

```python
store = MessageStore("agent.db")
sid = store.create_session("user_123")

# 每次用户输入
round_idx = store.start_round(sid, user_content)

# agent loop 执行，收集 events
events = []
async for event in agent.run(user_input):
    events.append(event.to_dict())
    if event.type == "response":
        final_response = event.content

# 执行完毕，持久化
store.complete_round(sid, round_idx,
    ai_content=[{"type": "text", "content": final_response}],
    trajectory=events,
)
```

### 与 Memory 系统配合

`SqliteExpiredContentStore` 适配器可将 L1 折叠的完整内容持久化到 session metadata 中：

```python
from common.agent_framework.message_store import MessageStore, SqliteExpiredContentStore

store = MessageStore("agent.db")
sid = store.create_session("user_123")

expire_store = SqliteExpiredContentStore(store, sid)
ref_id = expire_store.save("被折叠的完整内容...", "tool")
content = expire_store.load(ref_id)  # 通过 ref_id 取回
```

### 跨 Session 用户画像

```python
# 写入
store.set_user_memory("user_123", {
    "preferences": {"language": "zh", "style": "concise"},
    "facts": ["用户是后端工程师", "偏好 Python"],
}, version=1)

# 读取
mem = store.get_user_memory("user_123")
print(mem.data["preferences"])
```

## SQLite 表结构

| 表 | 说明 |
|----|------|
| `users` | 用户表 (`user_id`, `created_at`) |
| `sessions` | 会话表 (`session_id`, `user_id`, `metadata` JSON) |
| `messages` | 轮次表 (`session_id`, `round_idx`, `user_content`, `ai_content`, `trajectory`) |
| `user_memory` | 跨 session 记忆 (`user_id`, `version`, `data` JSON) |
| `schema_meta` | schema 版本追踪 |

数据库使用 WAL 模式，支持并发读取。通过 `check_same_thread=False` 支持多线程访问（写操作由 SQLite 内部锁保护）。

## 测试

```bash
python3 -m pytest common/agent_framework/tests/test_message_store.py -v
```

交互式 chatbot 演示：

```bash
python3 -m common.agent_framework.tests.chatbot_server --port 8680
# 打开 http://127.0.0.1:8680
```
