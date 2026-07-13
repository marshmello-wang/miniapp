# app-skill v0.3 协议

## 1. 传输模型

每个 Action 使用一个 HTTP POST 发起，并在该 POST 的响应体中以 `text/event-stream` 持续返回事件，直到 `done`。

```text
POST /api/runtime/actions
Content-Type: application/json

{
  "data_type": "app.agent",
  "appId": "fortune-teller",
  "intent": "开始占卜",
  "requestId": "req-001"
}

HTTP/1.1 200 OK
Content-Type: text/event-stream

data: {"data_type":"app.event","data":{"type":"thinking",...}}

data: {"data_type":"app.event","data":{"type":"ui_update",...}}

data: {"data_type":"app.event","data":{"type":"done",...}}
```

取消仍在执行的 Action：

```text
POST /api/runtime/actions/{requestId}/cancel
```

## 2. Action 类型

| data_type | 用途 |
|---|---|
| `app.init` | 挂载小程序，返回 `app.resource` |
| `app.call` | direct_action |
| `app.agent` | agent_action |
| `chat.send` | 通用 Chat 对话 |

## 3. 事件信封

```json
{
  "data_type": "app.event",
  "data": {
    "type": "ui_update",
    "appId": "fortune-teller",
    "appSession": "session-id",
    "requestId": "req-001",
    "seq": 2,
    "ts": 1780000000,
    "payload": {
      "structuredContent": {}
    }
  }
}
```

- `requestId`：前端预生成，关联一次 Action 及其 SSE 响应。
- `seq`：同一 Action 内的事件顺序。
- `appId`：App 路由字段，便于 Host 在多 iframe 场景下过滤。

## 4. 典型事件序列

```text
direct: ui_update* → done

agent: thinking* → tool_call* → tool_result*
       → ui_update* → text* → done

chat: text* → tool_call* → done
```

## 5. 脚本 Tool Result Metadata

应用脚本不通过 stdout 发送 UI 协议，而是写入每次调用独享的临时结果文件：

```text
MINIAPP_RESULT_PATH=/tmp/miniapp-result-xxxx.ndjson
```

脚本 SDK：

```python
from miniapp_runtime import emit_ui, end_turn

emit_ui({"phase": "question", "question": {...}})
end_turn()
```

NDJSON 事件：

```json
{"type":"ui_update","structuredContent":{}}
{"type":"agent_signal","agentSignal":"end_turn"}
```

Runtime 在 Bash 进程结束后读取并聚合为：

```json
{
  "uiUpdates": [{}],
  "agentSignal": "end_turn"
}
```

该 metadata 进入 Tool Result 的 `metadata.miniapp`，不会序列化给模型。Protocol Adapter 将其转换为 `ui_update` 事件；`agentSignal:end_turn` 仅用于停止 React Loop。

direct_action 则在 sandbox 完成后直接按 `uiUpdates` 顺序发送 `ui_update`。

## 6. 边界

- 不建立常驻 SSE 连接。
- 不解析 Bash stdout 中的 `structuredContent` 或 `agentSignal`。
- 当前 Demo 为单用户 MVP，未定义跨请求重放与幂等键。
