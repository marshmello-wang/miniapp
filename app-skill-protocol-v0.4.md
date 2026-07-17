# app-skill v0.4 协议

PC 端统一 Conversation、单一 Agent、Conversation SSE 事件流。不要求兼容 v0.3。

## 1. 架构概览

- **Command**：客户端通过 HTTP POST 提交 Action、Snapshot、Cancel。
- **Event**：Chat 与 UI Host 共同订阅 Conversation 级持续 SSE。
- **Agent Lane**：同一 Conversation 内 Agent Action 严格 FIFO。
- **Direct Lane**：Direct Action 立即执行，不经过 LLM，不进入 Agent Context。

一个 Conversation 对应一次 Chat。右栏 UI 是 Agent 的工具面，不是独立 Agent。

## 2. HTTP API

### 2.1 提交 Action

```http
POST /api/conversations/{conversationId}/actions
Content-Type: application/json
```

```json
{
  "actionId": "act_123",
  "kind": "agent",
  "source": "chat",
  "skillId": "order-review",
  "uiInstanceId": "ui_123",
  "intent": "批准当前订单",
  "name": "approve_order",
  "args": {},
  "expectedRevision": 17
}
```

| 字段 | 说明 |
|------|------|
| `actionId` | 客户端生成，幂等键 |
| `kind` | `agent` \| `direct` |
| `source` | `chat` \| `ui` |
| `intent` | Agent Action 用户意图 |
| `name` | Direct Action 脚本名 |
| `args` | Direct Action 参数 |
| `skillId` | 关联 Skill |
| `uiInstanceId` | 关联 UI 实例 |
| `expectedRevision` | UI 乐观锁版本 |

重复 `actionId` 返回 `409`。

Direct Action 响应示例：

```json
{ "status": "completed" }
```

Agent Action 响应示例：

```json
{ "status": "enqueued", "queuePosition": 1 }
```

### 2.2 回传 UI View Snapshot

```http
POST /api/conversations/{conversationId}/actions/{actionId}/snapshot
Content-Type: application/json
```

```json
{
  "snapshotRequestId": "snap_req_123",
  "uiInstanceId": "ui_123",
  "skillId": "order-review",
  "route": "/orders/1042",
  "revision": 19,
  "env": {
    "selectedOrderId": "1042",
    "filter": "pending"
  }
}
```

Runtime 校验 View Snapshot 后调用 Skill `context_snapshot` projector，生成 Business Context 供 Agent 使用。

### 2.3 取消 Action

```http
POST /api/conversations/{conversationId}/actions/{actionId}/cancel
```

```json
{ "conversationId": "conv_123", "actionId": "act_123", "cancelled": true }
```

### 2.4 订阅 Conversation SSE

```http
GET /api/conversations/{conversationId}/events?after={conversationSeq}
Accept: text/event-stream
```

断线后使用最后确认的 `conversationSeq` 重连并重放。

## 3. Durable Event Envelope

```json
{
  "eventId": "evt_123",
  "conversationId": "conv_123",
  "conversationSeq": 128,
  "actionId": "act_123",
  "actor": "runtime",
  "type": "ui.snapshot.requested",
  "skillId": "order-review",
  "uiInstanceId": "ui_123",
  "ts": 1780000000.0,
  "payload": {}
}
```

必需字段：

- `eventId`：全局唯一
- `conversationId`
- `conversationSeq`：Conversation 内单调递增
- `actor`：`user` \| `agent` \| `tool` \| `runtime`
- `type`
- `ts`
- `payload`

## 4. 主要事件类型

**Action 生命周期**

- `action.accepted`
- `agent_action.enqueued`
- `agent_action.started`
- `agent_action.completed`
- `agent_action.failed`
- `agent_action.cancelled`
- `direct_action.started`
- `direct_action.completed`
- `direct_action.failed`

**Snapshot**

- `ui.snapshot.requested`
- `ui.snapshot.received`
- `ui.snapshot.failed`

**Agent / Tool**

- `skill.loaded`
- `agent.text`
- `agent.thinking`
- `agent.tool.called`
- `agent.tool.completed`
- `agent.tool.failed`
- `agent.turn.completed`

**UI**

- `ui.resource.opened`
- `ui.command`
- `ui.state.changed`
- `ui.loading.changed`
- `ui.closed`

流式 token/thinking delta 可作为 transient SSE 帧发送，不占用 `conversationSeq`，不参与断线重放。

## 5. 典型事件序列

### 5.1 Chat Agent Action（无 UI）

```text
action.accepted
agent_action.enqueued
agent_action.started
agent.text*
agent_action.completed
```

### 5.2 UI Agent Action（有 Snapshot）

```text
action.accepted
agent_action.enqueued
ui.loading.changed (loading=true)
agent_action.started
ui.snapshot.requested
ui.snapshot.received
agent.text* / agent.tool.* / ui.command*
agent_action.completed
ui.loading.changed (loading=false)
```

### 5.3 Direct Action

```text
action.accepted
direct_action.started
ui.command*
direct_action.completed
```

Direct Action 记录进入 Event Log，但不进入后续 Agent Context。

## 6. UI Command Envelope

Agent 或 Direct Action 通过统一 envelope 更新右栏：

```json
{
  "type": "ui_command",
  "skillId": "order-review",
  "uiInstanceId": "ui_123",
  "command": "open",
  "route": "/orders/1042",
  "payload": {},
  "expectedRevision": 17
}
```

标准 command：

- `open`
- `navigate`
- `show_content`
- `patch`
- `close`

## 7. 脚本结果旁路

继续复用 `MINIAPP_RESULT_PATH` NDJSON 机制。stdout 仅用于模型可读摘要，不作为 UI 协议。

NDJSON 示例：

```json
{"type":"ui_command","command":"patch","payload":{},"expectedRevision":17}
```

Direct Action 与 Agent Tool 共用该格式。

Skill 可选提供 `context_snapshot` 脚本，由 Runtime 在 Agent Action 出队执行时调用，输出权威 business context。

## 8. Context 规则

- 用户 intent 作为原始 User Message 进入模型，不加 `[USER_INTENT]` 包裹。
- 有 UI 时，Business Context 作为独立 runtime 数据块进入模型。
- 无 UI 时，不发送空 runtime context。
- `load_skill` 不自动打开 UI；只有后续 `ui.command` 才影响右栏。
- Agent 普通文本显示在 Chat；AI 生成的右栏内容必须经 UI CLI。

## 9. 并发规则

- Agent Action：per-conversation FIFO；Chat 与 UI 共用同一队列。
- UI Agent Action 从入队到完成：UI loading，禁止 Direct Action。
- Chat Agent 运行期间：Direct Action 可立即执行。
- 所有 UI 提交携带 `expectedRevision`；冲突返回 `STALE_UI_REVISION`。

## 10. 边界

- 不兼容 v0.3 的 `app.event` / `chat.event` 每 Action 响应 SSE。
- 不在通用 Runtime 中实现 Skill 业务逻辑。
- Direct Action 不唤醒 Agent。
- 业务数据库按 `user × skill` 持久化；Conversation 状态相互隔离。
