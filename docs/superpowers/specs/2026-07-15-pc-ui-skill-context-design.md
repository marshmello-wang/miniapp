# PC UI Skill 上下文与统一事件流设计

## 1. 摘要

PC 端的 Chat 中栏与小程序右栏共享同一个 Conversation 和同一个 Agent。右栏不是独立 Agent，而是该 Agent 可观察、可调用的 UI Surface。

系统采用两条执行通道：

- Agent Lane：Chat 与 UI 发起的 Agent Action 按 Conversation 严格串行。
- Direct Lane：Direct Action 不经过模型，由通用 Direct Relay 转发到 Skill Sandbox。

所有操作进入同一条持久化 Conversation Event Log，但 Event Log 不等于模型 Context。Direct Action 只记录、不进入模型历史；每次 Agent Action 真正获得执行权时，Runtime 采集 UI View Snapshot，再调用 Skill-owned Context Projector 生成权威业务上下文，最终构建不可变 Turn Context。

协议采用 Command/Event 分离：

- 客户端通过 HTTP POST 提交 Action、Snapshot 和取消请求。
- Chat 与 UI 共同订阅 Conversation 级持续 SSE。
- SSE 支持按 `conversationSeq` 断线重放。

本设计按理想态定义，不要求兼容 app-skill v0.3 的 wire protocol。

## 2. 目标

1. 保持标准 `load_skill` 范式：加载 Skill 只加载指令与能力，不自动打开 UI。
2. Chat 与 UI 共享唯一 Agent、唯一历史和唯一 Loaded Skills 状态。
3. 所有用户操作和系统结果按因果顺序进入统一事件流。
4. 模型 Context 可控，不因高频 Direct Action 和原始 UI 事件无限增长。
5. Direct Action 保持低延迟、确定性，且不与具体小程序业务耦合。
6. 模型普通文本只展示在 Chat；右栏 AI 内容只能通过 Skill 声明的 UI CLI 产生。
7. 支持 Agent Action 排队、执行时快照、状态版本检查和断线恢复。

## 3. 非目标

- 不把 DOM、视觉细节或每次输入事件发送给模型。
- 不让 Direct Action 自动唤醒模型；需要模型参与的动作本身就是 Agent Action。
- 不在通用 Runtime 中实现任何具体小程序业务逻辑。
- 不保证跨 Conversation 的 Agent Action 串行。
- 不要求兼容 v0.3 的 `app.event`、`chat.event` 或每 Action 响应 SSE。

## 4. 核心概念

### 4.1 Conversation

Conversation 对应一次 Chat，会随新建 Chat 相互隔离。它拥有：

- 单调递增的 Conversation Event Log
- 唯一 Agent Lane
- Agent 对话历史和工具轨迹
- Loaded Skills Projection
- 每个 Skill 的 UI 实例状态与路由

### 4.2 Skill 持久数据

Skill 的业务数据库按 `user × skill` 持久化，可跨 Conversation 使用。数据库事务和业务冲突语义由 Skill 自己定义。

### 4.3 UI Instance

UI Instance 按 `conversation × skill` 隔离，至少包含：

- `uiInstanceId`
- `skillId`
- 当前 route
- 当前 `uiRevision`
- 可恢复的 UI Projection
- 当前负责提供快照的 Host 连接

### 4.4 Action

Action 是一次用户意图或确定性调用：

- Agent Action：进入 Agent Lane，由唯一 Agent Worker 执行。
- Direct Action：进入 Direct Lane，由 Direct Relay 立即转发。

### 4.5 Event 与 Context

- Event Log 是完整、可审计、可重放的事实记录。
- Turn Context 是 Agent Action 执行时对事实的受控投影。

Direct Action 的 requested/completed/failed 事件存在于 Event Log，但不进入 Agent Context。其业务结果通过当前 UI Snapshot 或 Skill 工具按需查询体现。

## 5. 总体架构

### 5.1 Conversation Runtime

Conversation Runtime 是确定性协调层，负责：

- 接收和持久化 Action
- 分配 `conversationSeq`
- 维护 per-conversation Agent FIFO
- 管理 UI Agent Action 的 loading/lock
- 在 Agent Action 出队时请求 UI Snapshot
- 构建不可变 Turn Context
- 调用 Agent Worker
- 持久化 Agent 和 Tool 语义事件
- 维护 Loaded Skills、UI State 等 Projection
- 向 Conversation SSE 广播并重放事件

Conversation Runtime 不执行模型推理，也不理解 Skill 业务。

### 5.2 Agent Worker

Agent Worker 是唯一模型执行者，负责：

- 使用 Conversation 的 Agent 历史继续推理
- 通过标准 `load_skill` 工具加载 Skill
- 调用 Skill 工具和脚本
- 输出 Chat 文本
- 通过已加载 Skill 声明的 UI CLI 操作右栏

加载 Skill 本身不得挂载或打开 UI。

### 5.3 Direct Relay

Direct Relay 是与具体 Skill 无关的协议旁路，只负责：

1. 校验通用 Action envelope、身份、权限和 revision。
2. 按 `skillId + actionName` 从 Registry 解析脚本入口。
3. 把参数转发给通用 Sandbox Executor。
4. 原样转发标准化 UI Command/Patch。
5. 把 requested/completed/failed 写入 Event Log。

Direct Relay 禁止：

- 包含具体小程序的业务分支
- 理解或重写业务 payload
- 构造 Agent Context
- 调度或唤醒 Agent
- 自行决定页面、路由或展示内容

### 5.4 Skill Registry 与 Sandbox Executor

Skill Registry 解析 Skill Manifest、脚本、权限、UI route 和 schema。

Sandbox Executor 提供通用隔离执行环境，并注入：

- Skill 持久数据库路径
- 每次调用独享的结果文件
- Conversation、Skill 和 UI Instance 的只读调用元数据

## 6. Skill 与 UI 契约

### 6.1 Skill Package

一个带 UI 的 Skill 至少包含：

- `SKILL.md`
  - 业务能力
  - 何时只在 Chat 回复
  - 何时应打开或更新 UI
  - 可用 UI CLI、route 和参数示例
- Skill Manifest
  - 脚本与 visibility
  - 权限
  - UI bundle 入口
  - route、command、view snapshot 和 business context schema
- Skill-owned CLI 或脚本
- Skill-owned `context_snapshot` projector
- UI bundle
- 持久数据 schema 或数据库初始化逻辑

模型只有在加载 Skill 后，才从 `SKILL.md` 获知该 Skill 的 UI CLI 和 route。

### 6.2 UI CLI

UI CLI 可以由 Skill 自己提供，但输出统一的 `ui_command` envelope：

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

标准 command 至少支持：

- `open`
- `navigate`
- `show_content`
- `patch`
- `close`

Runtime 只验证 envelope 和 Manifest schema，不解释业务 payload。

### 6.3 脚本结果旁路

继续复用独享 NDJSON 结果文件的机制，禁止解析 stdout 作为 UI 协议。stdout 仅用于模型可读的普通工具摘要。

NDJSON 可包含：

```json
{"type":"ui_command","command":"show_content","route":"/result","payload":{},"expectedRevision":17}
```

Direct Action 和 Agent Tool 均可通过相同的结果文件格式返回 UI Command。

### 6.4 双层 Snapshot

Snapshot 分为两层：

1. UI View Snapshot
   - 由 Skill UI 注册的 snapshot provider 生成。
   - 只描述 route、选择项 ID、筛选条件、表单草稿和 `uiRevision` 等临时界面状态。
   - 属于不可信客户端输入，不得作为业务写入的权威依据。
2. Business Context Snapshot
   - 由 Skill-owned `context_snapshot` projector 确定性生成，不经过 LLM。
   - 接收 View Snapshot，并查询 `user × skill` 持久数据库。
   - 输出当前 Agent Turn 所需的权威业务摘要。

Runtime 只负责调用 projector、校验输入输出 schema 和组装 Context，不理解业务字段。普通业务写操作仍由 Skill scripts/tools 执行，并必须重新读取数据库完成授权、状态和并发校验。

## 7. 输出路由

输出位置由输出类型决定，而不是由 Action 来源决定：

- Agent 普通文本：只进入 Chat Surface。
- Agent UI CLI：只进入对应 UI Surface。
- Direct Action UI Patch：只进入对应 UI Surface。
- Tool trajectory：进入 Event Log 和 Debug Projection，不默认展示给普通用户。

因此，即使 Agent Action 由右栏发起，模型直接输出的文字仍显示在左栏；模型若希望结果显示在右栏，必须调用 Skill UI CLI。

## 8. Command 协议

### 8.1 提交 Action

```http
POST /api/conversations/{conversationId}/actions
Content-Type: application/json
```

```json
{
  "actionId": "act_123",
  "kind": "agent",
  "source": "ui",
  "skillId": "order-review",
  "uiInstanceId": "ui_123",
  "intent": "批准当前订单",
  "args": {
    "orderId": "1042"
  },
  "expectedRevision": 17
}
```

Agent Action 使用 `intent` 表达用户目的。Direct Action 使用 `name + args` 指定 Manifest 中声明的确定性脚本。

服务端对 `actionId` 提供幂等语义。同一 `actionId` 重试不得重复执行。

### 8.2 回传 UI View Snapshot

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
    "filter": "pending",
    "visibleOrder": {
      "id": "1042",
      "status": "pending"
    }
  }
}
```

View Snapshot 必须符合 Skill Manifest schema 和大小上限，不包含 DOM 或完整业务记录。Runtime 收到后调用 Skill-owned `context_snapshot` projector；projector 查询持久数据库并输出符合 business context schema 的模型上下文。

### 8.3 取消 Action

```http
POST /api/conversations/{conversationId}/actions/{actionId}/cancel
```

排队中的 Agent Action 可直接取消。运行中的 Agent Action采用协作式取消，并记录最终状态。

## 9. Conversation SSE

### 9.1 订阅

```http
GET /api/conversations/{conversationId}/events?after={conversationSeq}
Accept: text/event-stream
```

Chat 与 UI Host 订阅同一条 SSE。断线后使用最后确认的 `conversationSeq` 重连并重放。

### 9.2 Durable Event Envelope

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
  "ts": "2026-07-15T09:00:00Z",
  "payload": {}
}
```

必需字段：

- `eventId`：全局唯一，用于去重。
- `conversationId`：事件所属 Conversation。
- `conversationSeq`：Conversation 内严格递增。
- `actor`：`user | agent | tool | runtime`。
- `type`：语义事件类型。
- `ts`：服务端时间。

可选因果字段：

- `actionId`
- `parentEventId`
- `skillId`
- `uiInstanceId`
- `toolCallId`

### 9.3 主要事件类型

Action 生命周期：

- `action.accepted`
- `agent_action.enqueued`
- `agent_action.started`
- `agent_action.completed`
- `agent_action.failed`
- `agent_action.cancelled`
- `direct_action.started`
- `direct_action.completed`
- `direct_action.failed`

Snapshot：

- `ui.snapshot.requested`
- `ui.snapshot.received`
- `ui.snapshot.failed`

Agent 与 Tool：

- `skill.loaded`
- `agent.text`
- `agent.tool.called`
- `agent.tool.completed`
- `agent.tool.failed`

UI：

- `ui.resource.opened`
- `ui.command`
- `ui.state.changed`
- `ui.loading.changed`
- `ui.closed`

流式 token、thinking delta 和心跳不是 Durable Event。它们可作为 SSE transient event 发送，但不占用 `conversationSeq`，也不参与断线重放。最终文本、工具结果和状态变更必须持久化。

## 10. Turn Context

Agent Action 获得 Agent Lane 后，Runtime 按以下顺序构建 Context：

1. Agent system prompt。
2. Conversation 的 Agent 对话历史与标准工具轨迹。
3. Loaded Skills Projection 中的 Skill 指令与工具契约。
4. 当前 UI 的 Business Context Snapshot；仅在 UI 存在时加入。
5. 本次 Action 的原始用户意图和结构化参数。

用户意图按原文作为普通 User Message 进入模型，不添加 `[USER_INTENT]` 等前后包裹。

UI 存在时，Business Context Snapshot 作为独立 Runtime Context 数据块进入模型。它是数据而非指令，优先级低于 system prompt 和 Skill 指令。示例：

```yaml
context_version: 1
skill_id: order-review
ui_instance_id: ui_123
route: /orders/1042
ui_revision: 19
view:
  selected_order_id: "1042"
  has_unsaved_draft: false
business:
  order:
    id: "1042"
    status: pending
    amount: 12800
    currency: CNY
  risk_flags:
    - high_value
  allowed_actions:
    - approve
    - reject
```

没有打开 UI 时，Runtime 完全省略 Runtime UI Context 数据块，不发送 `active_ui: null` 或任何空占位。

明确排除：

- Direct Action 逐条历史
- DOM 和视觉状态
- 原始点击、hover、键盘事件
- 未经 Context Projector 校验和投影的前端业务字段
- SSE token delta
- 与当前 Agent 历史无关的审计细节

`skill.loaded` 会更新 Loaded Skills Projection。后续 Turn 重建 Context 时恢复对应 Skill 指令，因此 Skill 加载状态属于 Conversation，而不是某个 UI 实例。

## 11. Agent Action 时序

### 11.1 UI 发起

1. UI POST Agent Action。
2. Runtime 持久化 Action 并写 `agent_action.enqueued`。
3. UI 收到事件后立即进入 loading，禁止 Direct Action。
4. Action 获得 Agent Lane。
5. Runtime 写 `ui.snapshot.requested`。
6. 当前 UI Host 调用 Skill UI 的 snapshot provider 并 POST View Snapshot。
7. Runtime 校验 View Snapshot，调用 Skill-owned `context_snapshot` projector。
8. Projector 查询持久数据库并返回 Business Context Snapshot。
9. Runtime 校验并固定 Business Context Snapshot，写 `ui.snapshot.received`。
10. Context Builder 生成不可变 Turn Context。
11. Agent Worker 执行。
12. 普通文本写 `agent.text`；UI CLI 写 `ui.command`。
13. Runtime 写 completed/failed，解除 loading。

### 11.2 Chat 发起

步骤与 UI 发起相同，但提交后不必锁定 UI。Chat Agent 运行期间，Direct Action 可以立即执行。

如果 Chat Agent 使用旧 Snapshot 提交 UI Command，Commit Gate 通过 `expectedRevision` 检测冲突，并把 `STALE_UI_REVISION` 作为标准 Tool Result 返回 Agent。

## 12. Direct Action 时序

1. UI POST Direct Action，携带 `expectedRevision`。
2. Runtime 检查该 UI 是否因 UI Agent Action 排队或运行而锁定。
3. 锁定时拒绝执行。
4. 未锁定时 Direct Relay 解析 Manifest action。
5. Direct Relay 获取对应 UI Instance 的 Commit Gate，并在执行脚本前校验 revision。
6. Sandbox Executor 在 Commit Gate 内运行脚本；期间其他 UI Command 可以等待，但不能插入提交。
7. 脚本通过结果文件返回标准 UI Command/Patch。
8. Runtime 校验结果、提交 UI Projection 并递增 revision。
9. Runtime 写 completed/failed Event。
10. UI 应用新 Projection。
11. 不调度 Agent，不把 Action 写入模型历史。

Commit Gate 只保证同一 UI Instance 的 UI 提交顺序，不承诺业务数据库与 UI Projection 之间的分布式原子事务。Skill 脚本必须自行使用数据库事务；若数据库已提交但结果文件或 UI Patch 校验失败，Runtime 记录部分失败并要求 UI 从当前业务状态重新生成 Snapshot。

## 13. 并发与一致性

### 13.1 Agent Lane

- 每个 Conversation 只有一个 Agent Lane。
- Chat 与 UI Agent Action 共用同一 FIFO。
- Agent Context 在 Action 开始执行时固定，运行中不增量注入新事件。

### 13.2 Direct Lane

- Direct Action 可与 Chat Agent Action 并行。
- UI Agent Action 从入队到完成期间锁定对应 UI，禁止插入 Direct Action。
- Direct Action 不进入 Agent Lane。

### 13.3 Revision

所有 UI Command 和 Direct Action 都携带 `expectedRevision`。

- 匹配：提交后 `uiRevision + 1`。
- 不匹配：拒绝提交并返回 `STALE_UI_REVISION`。
- 不允许 last-write-wins 静默覆盖。

Agent 收到 stale Tool Result 后可请求最新 Snapshot，再决定重试或放弃。

### 13.4 Skill 数据库

`user × skill` 数据库可能被多个 Conversation 并发访问。Runtime 只提供通用调用隔离和数据库连接边界；事务、唯一约束和领域冲突由 Skill 实现。

## 14. 失败处理

### 14.1 Snapshot

- UI 未打开：完全省略 Runtime UI Context，不生成空 Snapshot。
- Host 断线或超时：Agent Action 失败为 `UI_SNAPSHOT_UNAVAILABLE`，除非该 Action 明确允许无 UI 继续。
- View Snapshot schema 不合法：拒绝并记录 `ui.snapshot.failed`。
- Context Projector 失败或 Business Context schema 不合法：拒绝启动模型并记录 `ui.snapshot.failed`。

### 14.2 Direct Action

- 脚本失败：记录 `direct_action.failed`，右栏显示确定性错误。
- revision 在脚本执行前检查；冲突时不运行脚本，因此不产生 UI 或业务变更。
- 脚本已经提交数据库、但 UI 结果无效时：记录部分失败，保留业务提交，并要求 UI 刷新当前业务状态。
- 失败不唤醒 Agent。

### 14.3 Agent Turn

- 模型或工具失败：记录 `agent_action.failed`。
- 保留最后已提交 UI Projection。
- UI Agent Action 必须解除 loading。
- UI CLI 失败作为 Tool Result 返回 Agent，允许在同一 Turn 内恢复。

### 14.4 SSE 与重放

- 客户端保存最后处理的 `conversationSeq`。
- 重连时通过 `after` 请求缺失 Durable Events。
- 客户端按 `eventId` 去重。
- Transient events 丢失不影响状态恢复。

## 15. 安全与校验

- Host 必须校验 iframe message 的 `source`、目标 Window 和 UI Instance。
- Runtime 校验用户对 Conversation、Skill 和 UI Instance 的访问权限。
- Manifest schema 校验 Direct Action、UI Command 和 Snapshot。
- NDJSON 结果文件保持独享、大小受限、严格 JSON 校验。
- 禁止解析 stdout 作为结构化 UI 协议。
- `actionId` 幂等，防止网络重试重复执行。
- UI Command 只能发送到当前 Conversation 中匹配的 UI Instance。

## 16. 代码复用策略

本设计不复用 v0.3 wire protocol，但复用成熟实现：

可直接保留或抽取：

- Agent framework 与 `load_skill`
- Sandbox Executor
- `MINIAPP_RESULT_PATH` 临时结果文件
- NDJSON 大小限制、JSON 和 UTF-8 校验
- Manifest 扫描、script visibility 和 permissions
- iframe `postMessage` 的 Window/source 校验
- Agent content block 到 text/tool 语义事件的适配逻辑

需要重构：

- `RuntimeService`：从 per-request producer 变为 Conversation Runtime、Event Store 和 Agent Lane。
- `HostBridge`：从每 Action SSE 变为 Conversation SSE 订阅和 Snapshot 响应器。
- `miniapp.js`：Agent Action 不再提交预采 env；改为响应 `ui.snapshot.requested`。
- `protocol.py`：统一 Durable Event 与 Transient Event，不再区分 app/chat frame。
- `stores.py`：拆分 Conversation Event Store、Projection Store 和 `user × skill` Persistent Store。
- App Manifest：增加 UI route、command 和 snapshot schema。

需要删除：

- 独立 `MiniAppEngine.agent_action`
- 小程序独立 Agent 历史
- Chat 中的 `activeSkill.skillHistory` 拼接
- load/mount 时自动打开 UI
- `on_init.user_message` 自动触发 Agent
- Direct Action 写入模型历史

## 17. 验收测试

### 17.1 Skill 与输出路由

1. `load_skill` 成功后右栏不自动打开。
2. Agent 调用 UI CLI 后打开指定 Skill 和 route。
3. Agent 普通文本只出现在 Chat。
4. Agent 调用 `show_content` 后内容只出现在 UI。

### 17.2 Context

1. Direct Action 被完整记录，但后续 Turn Context 不含其事件历史。
2. UI View Snapshot 只包含临时界面状态，不被当作权威业务数据。
3. Context Projector 能反映 Direct Action 写入数据库后的最新业务状态。
4. 用户意图以原始 User Message 进入模型，不添加前后包裹。
5. 没有 UI 时不生成 Runtime UI Context 空占位。
6. Agent 可通过 Skill 工具查询 Direct Action 写入的持久数据。
7. 新建 Chat 不继承旧 Conversation 的 Agent、UI 或 Loaded Skills 状态。
8. 新建 Chat 可以访问同一 `user × skill` 持久数据库。

### 17.3 排队与并发

1. Chat 和 UI Agent Action 严格 FIFO。
2. UI Agent Action 排队期间 UI 进入 loading，并拒绝 Direct Action。
3. Action 出队后才请求 Snapshot。
4. Chat Agent 运行期间 Direct Action 可立即完成。
5. 旧 revision 的 Agent UI Command 不会覆盖 Direct Action 的新状态。

### 17.4 Event Stream

1. Chat 与 UI 从同一 SSE 收到相同顺序的 Durable Events。
2. 断线后按 `conversationSeq` 完整重放。
3. 重复事件按 `eventId` 去重。
4. Transient delta 丢失后，最终 Durable Event 仍可恢复正确 UI 和 Chat 状态。

### 17.5 失败恢复

1. Snapshot 超时会终止需要 UI 的 Agent Action，并解除 loading。
2. Direct Action 失败不会启动 Agent。
3. UI CLI schema 或 revision 错误会作为 Tool Result 返回 Agent。
4. Agent 失败后保留最后成功提交的 UI Projection。
5. 客户端重载后可由 Event Log 和 Projection 恢复当前界面。

## 18. 最终决策

- 一个 Conversation 只有一个 Agent。
- UI 是 Agent 的工具与观察面，不是 Agent。
- `load_skill` 不打开 UI。
- AI 文本进入 Chat；AI UI 内容必须经 Skill UI CLI。
- Direct Action 只记录、不进入 Context、不唤醒 Agent。
- Agent Action 执行时采集 UI View Snapshot，并由 Skill Context Projector 生成进入模型的权威业务上下文。
- 用户意图不添加格式包裹；无 UI 时不注入空 Runtime UI Context。
- UI Agent Action 排队期间锁定 UI。
- Agent Action per-conversation 串行，Direct Action 可与 Chat Agent 并行。
- 业务数据库按 `user × skill` 持久化，Conversation 状态相互隔离。
- 采用 Command POST + Conversation SSE + Durable Event Replay。
- 不要求兼容 v0.3 协议，仅复用成熟代码模块。
