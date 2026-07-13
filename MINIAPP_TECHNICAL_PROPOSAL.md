# MiniApp 技术方案

## 1. 核心定位

MiniApp 不是“在聊天中嵌入网页”，也不是让模型临时生成 UI，而是一种面向 Agent 的可运行应用单元：

```text
MiniApp = app.yaml + SKILL.md + scripts/ + assets/ui/ + assets/schema/
```

- `app.yaml`：声明入口、版本、脚本、权限与生命周期；
- `SKILL.md`：定义 Agent 的领域知识和工作流；
- `scripts/`：承载可测试、可复现的确定性业务逻辑；
- `assets/ui/`：提供专用 H5 交互界面；
- `assets/schema/`：提供 session 级业务数据模板。

宿主 Runtime 统一提供 iframe、Agent、脚本执行、会话存储、流式协议和调试能力。

核心原则：

> 该确定的部分保持确定，该推理的部分交给 Agent。

---

## 2. 技术架构

```text
┌─────────────────────────────────────────────┐
│ 表现层                                      │
│ Workbench / Chat / Overlay / Standalone     │
├─────────────────────────────────────────────┤
│ 客户端 Runtime                              │
│ iframe / miniapp.js / HostBridge / POST+SSE │
├─────────────────────────────────────────────┤
│ 后端引擎                                    │
│ WSHandler / MiniAppEngine / ChatEngine      │
├─────────────────────────────────────────────┤
│ 执行与状态                                  │
│ ReactAgent / Sandbox / MessageStore         │
├─────────────────────────────────────────────┤
│ MiniApp 应用包                              │
│ Manifest / Skill / Scripts / UI / Schema    │
└─────────────────────────────────────────────┘
```

### 三方职责

**Widget**

- 渲染 UI；
- 发起 direct_action 或 agent_action；
- 消费流式事件；
- 上报当前界面语义状态。

**Host Runtime**

- 管理 iframe 生命周期；
- 通过 HostBridge 桥接 iframe 与后端；
- 注入 `appId` 和 `sessionId`；
- 处理路由、权限与调试。

**Backend Runtime**

- 加载应用包；
- 执行 Script 或 Agent；
- 持久化上下文和业务状态；
- 产出统一事件流。

---

## 3. 双路径执行模型

### direct_action

不经过模型，直接执行注册脚本：

```text
Widget
  → miniapp.directAction
  → app.call
  → Sandbox Script
  → structuredContent
  → ui_update
  → done
```

适合查询、保存、批准、刷新等原子操作。

主要优势：

- 无 token 成本；
- 延迟稳定；
- 结果可重复；
- 易于测试和审计。

执行完成后，Runtime 将动作摘要写入当前 session，供后续 Agent 读取。

### agent_action

由模型结合 Skill、历史、界面状态与工具进行推理：

```text
Widget
  → miniapp.agentAction(intent, focus, env)
  → app.agent
  → MiniAppEngine
  → ReactAgent + SKILL.md + Tools
  → thinking / tool / text / ui_update
  → done
```

适合理解模糊需求、分析、动态问答和多步规划。

| 维度 | direct_action | agent_action |
|---|---|---|
| 是否经过 LLM | 否 | 是 |
| 主要执行者 | Script | ReactAgent |
| 确定性 | 高 | 受模型影响 |
| 成本与时延 | 低且稳定 | 较高且波动 |
| 典型用途 | 查询、保存、变更 | 理解、分析、规划 |

---

## 4. 关键协议

### 通信链路

```text
iframe
  ↔ postMessage
HostBridge
  → POST /api/runtime/actions
  ← text/event-stream (同一 Action 的响应)
Backend
```

### 上下行帧

| 方向 | 类型 | 用途 |
|---|---|---|
| 上行 | `POST app.init` | iframe 就绪和挂载握手 |
| 上行 | `POST app.call` | direct_action |
| 上行 | `POST app.agent` | agent_action |
| 上行 | `POST chat.send` | 通用 Chat 对话 |
| 上行 | `POST cancel` | 取消 request |
| 下行 | 同一 POST 的 SSE | `app.resource` / `app.event` / `chat.event` 直到 `done` |
| 下行 | Host 本地 | `debug` 上下行帧镜像 |

### 统一事件信封

```json
{
  "data_type": "app.event",
  "data": {
    "type": "ui_update",
    "appSession": "session-id",
    "requestId": "req-001",
    "seq": 3,
    "ts": 1780000000,
    "payload": {
      "structuredContent": {}
    }
  }
}
```

- `appSession`：目标 App session；
- `requestId`：关联本次 action；
- `seq`：同一 action 内的事件顺序；
- `type`：事件语义；
- `payload`：类型相关数据。

### 事件类型

| type | 语义 |
|---|---|
| `thinking` | Agent 推理增量 |
| `text` | 面向用户的正文 |
| `tool_call` | 工具调用开始 |
| `tool_result` | 工具调用结果 |
| `ui_update` | Widget 状态更新 |
| `done` | action 结束 |

典型事件流：

```text
direct: ui_update → done

agent: thinking* → tool_call* → tool_result*
       → ui_update* → text* → done
```

普通工具调用不会自动修改 Widget。只有 Agent 调用 `app_emit`，或 Script 通过 `miniapp_runtime.emit_ui()` 写入 Tool Result metadata，才会产生 `ui_update`。stdout 仅作为 Bash 的普通工具输出，不再承载 UI 协议。

---

## 5. structuredContent

`structuredContent` 是 Agent、Script 与 UI 之间的应用层契约：

```json
{
  "phase": "question",
  "question": {
    "text": "你目前最关心哪方面？",
    "type": "choice",
    "options": ["感情", "工作", "财运"]
  }
}
```

模型输出业务语义，UI 根据 schema 确定性渲染，而不是执行模型生成的 HTML。

这带来：

- Agent 与前端解耦；
- UI 行为稳定；
- schema 可独立测试；
- 多端可以使用不同 UI；
- 模型无法任意操作 DOM；
- 状态变化可直接调试。

当前 Demo 采用全量更新，尚未支持 `stateVersion`、JSON Patch 和断线重同步。

---

## 6. 会话连续性

对话与 Agent 轨迹存储于：

```text
~/.miniapp/messages.db
```

业务数据存储于：

```text
~/.miniapp/sessions/{sessionId}/
```

从 Chat 打开小程序时，Overlay 复用 Chat 的 session：

```text
Chat session
  → 打开 MiniApp
  → MiniApp 操作写入同一 session
  → 退出 MiniApp
  → Chat Agent 延续上下文
```

小程序内部轮次标记为 `source = miniapp:{appId}`。Chat UI 可以折叠显示这些交互，而 Agent 仍能读取完整历史。

通用 Chat Agent 负责发现和路由应用；专用 MiniApp Agent 负责领域执行。这避免将所有 Skill 塞入一个通用 Agent。

---

## 7. 技术优势与生态意义

### 关键优势

1. **确定性与智能按需组合**：原子操作不经模型，复杂任务才使用 Agent。
2. **UI 可控**：模型输出数据而不是 DOM，设计与交互可以测试和版本化。
3. **会话连续**：Chat、MiniApp、Script 动作和业务状态共享上下文。
4. **技术栈解耦**：模型、Agent、Host、UI 和传输实现可以独立替换。
5. **全链路可观测**：用户动作、推理、工具和 UI 更新处于同一事件时间线。
6. **应用包可分发**：Skill、Script、UI 和 Manifest 形成统一交付单元。

### 生态意义

传统 Agent 生态通常以 Prompt、Tool、API 或 Workflow 为交付单位。

MiniApp 将交付单元升级为：

```text
领域认知
+ 确定性执行
+ 专用 UI
+ 持久状态
+ 生命周期
```

开发者交付的不只是“Agent 能调用什么”，而是“用户如何完整使用这项能力”。

### 与 MCP 的关系

二者互补：

- MCP 解决 Agent 如何发现和调用远程能力；
- MiniApp 解决能力如何以完整用户体验运行和交付。

MiniApp 可以通过 MCP 调用远程服务，同时继续使用 app-skill 协议承载 UI、session 和生命周期。

---

## 8. 当前边界

当前项目是 Reference Demo，不是完整生产平台。

### 协议

- 正式协议文档为 [app-skill v0.3](../app-skill-protocol-v0.3.md)；
- 每个 Action 使用 `POST /api/runtime/actions`，响应为同一请求的 SSE 流；
- cancel 通过 `POST /api/runtime/actions/{requestId}/cancel` 中止仍在执行的请求。

### 安全

- iframe 同源且未启用严格 sandbox；
- postMessage 未严格校验 origin；
- direct_action 缺少 input schema、authz 和限流；
- Script 是宿主子进程，不是强隔离安全沙箱；
- 尚无完整多用户认证和授权体系。

### 可靠性与生态

- `ui_update` 没有状态版本；
- 无断线续传和幂等键；
- 无远程 Registry、包签名和回滚机制。

---

## 9. 生产化路线

### P0：协议收敛

- 发布正式 v0.3 规范；
- 明确语义协议与传输实现；
- 定义 success、error、cancelled 和 timeout；
- 建立 JSON Schema 与 conformance tests。

### P1：安全与多租户

- 正式身份与 session 映射；
- script input schema 和操作级 authz；
- iframe origin、CSP 与 sandbox；
- 强隔离 Script Runtime；
- 审计、限流与资源配额。

### P2：状态与可靠性

- `stateVersion` 和 JSON Patch；
- 幂等键；
- 断线恢复；
- 背压；
- action 超时与资源回收。

### P3：应用分发

- 远程 Registry；
- 语义版本与包签名；
- 权限审核；
- 灰度发布、升级与回滚。

### P4：开放互操作

- MCP Tool Binding；
- Host capability 协商；
- 远程 Sandbox；
- 多语言 SDK 与多宿主兼容。

---

## 10. 结论

MiniApp 定义了一种新的 Agent 应用抽象：

```text
领域认知 + 确定性执行 + 专用交互 + 持久状态 + 生命周期
```

其最重要的技术特点是：

1. direct_action 与 agent_action 双路径；
2. 统一流式事件协议；
3. tool_call 与 ui_update 显式分离；
4. structuredContent 作为 Agent 与 UI 的稳定契约；
5. Chat 与 MiniApp 共享 session。

它相对纯 Chatbot 更有界面和确定性，相对传统应用更有语言理解和动态编排，相对 MCP 更关注端到端体验，相对模型生成 UI 更稳定、更安全、更可测试。

下一阶段应优先完成协议定稿、安全模型、运行隔离、状态版本和断线恢复，再发展应用分发生态。
