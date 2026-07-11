# App Skill 协议设计 V0.2

## 1. 角色与术语

| 角色 | 定义 |
|---|---|
| **iframe / Widget** | App 的 UI 容器,iframe = widget |
| **客户端运行时 (Client Runtime)** | 客户端一侧承载 iframe 的外壳;与后端之间**上行用请求、下行用流**(见 §1) |
| **Agent** | 后端 Agent 服务(`work_agent_server`),内部跑 ReAct Loop(仅 `agent_action` 进这里) |
| **Sandbox Runtime** | App 脚本 / cli 的执行沙箱;`direct_action` 直连它执行;**Widget 生命周期与之绑定** |

三方拓扑:**iframe ↔ 客户端运行时 ↔ 后端(Agent / Sandbox)**

- iframe ↔ 客户端运行时:**Bridge**,JSON-RPC 2.0 over `postMessage`(天然双向)。
- 客户端运行时 ↔ 后端:**传输无关**。协议只要求"**上行可用请求、下行必须流式**"。推荐实现见 §1 的**方案 B**(上行 POST 触发 + 下行 per-run 流 + run 结束关流)。"不是 restful"仅针对**下行**(不能用一问一答建模),上行触发仍是普通请求。

**两条上行路径(第一期核心)**:

```text
                          ┌──────────── Agent (ReAct Loop) ────────────┐
                          │  agent_action(经 Model)                     │
 iframe ── 客户端 ────────┤                                            ├─ 流式下行 ─→ 客户端 ─→ iframe
                          │  direct_action(不经 Model,直连执行)         │
                          └──────────── Sandbox Runtime ───────────────┘
                                 (执行后旁路写一条 app.action 进会话历史)
```

> 图中「客户端」= **客户端运行时 (Client Runtime)**,见 §1。

---

## 2. 协议分层

| 编号 | 协议 | 方向 | 载体 | 分期 |
|---|---|---|---|---|
| Part 1 | Skill App 包规范 | Skill 包定义 | Sandbox Runtime | 一期 |
| Part 2 §1 | 传输与通信模型 | iframe ↔ 客户端运行时 ↔ 后端 | Bridge + 上行请求/下行流 | 一期 |
| Part 2 §2 | UI 资源下发 + 最小握手 | 后端 → Client | app-skill 协议 | 一期 |
| Part 2 §3 | UI 上行(direct/agent action) | UI → 后端 | Bridge + app-skill 协议 | 一期 |
| Part 2 §4 | Agent → UI 下行(统一事件流) | 后端 → UI | app-skill 协议 + Bridge | 一期 |
| Part 2 §5 | UI 现状作 env | UI → Model 上下文 | Bridge + app-skill 协议 | 一期 |
| Part 2 §6 | App 生命周期(静默释放) | — | Runtime + 客户端运行时 | 一期 |
| Part 3 | 安全 / 状态一致性 / 断线续传 / 深度协商 | — | — | **二期(仅列方向)** |

---

## 3. 端到端时序总览（推荐先读）

以"打开一个订单审核小程序"为例,从点入口到用户操作走一遍,先钉死分工再看时序。

### 3.1 谁负责什么

| 角色 | 职责 |
|---|---|
| **iframe / Widget** | 渲染小程序 UI;发起 `direct_action` / `agent_action`;消费事件流(`ui_update` 更新界面、叙事事件自定义呈现);采集本地 UI 快照;纯本地交互(Tab/折叠)自己消化 |
| **客户端运行时 (Client Runtime)** | 客户端一侧承载 iframe 的外壳;挂载/销毁 iframe;做 Bridge↔后端的桥接与路由;发 `load_app`;握手后触发首屏;**每次触发把 env 打包进请求**;管连接生命周期(开流/关流) |
| **Agent(后端 ReAct)** | **只处理 `agent_action`**;跑 ReAct loop;产出一条事件流(叙事事件 + 经脚本 emit 的 `ui_update`),末尾 `done`;run 结束关流释放 |
| **Sandbox Runtime** | 执行脚本/cli(`direct_action` 直连 + agent 内部工具);捕获显式 emit → 转 `ui_update` 事件;写 `app.action` 进历史;**widget 生命周期宿主** |
| **Store** | 存会话历史/上下文/业务数据;run 时 load、结束 write-back(所以内存不常驻,见附录 D) |

### 3.2 阶段 A — 打开入口 → 拉起 App（此时 iframe 还不存在）

1. **用户**点「订单审核」入口。
2. **客户端运行时 → 后端**:`load_app("order-review")`(确保 sandbox 会话在,加载 skill 包)。
3. **Sandbox Runtime**:读 `app.yaml`,注册 `scripts` 与资源,建 `appSession`。
4. **后端 → 客户端运行时**:下发 `app.resource`(uri / mimeType / manifest,**不含业务数据**)。
5. **客户端运行时**:据此创建 sandboxed iframe、注入 SDK、载入 `assets/ui/index.html`,先渲染**骨架**。

### 3.3 阶段 B — 握手 → 首屏数据（消除首帧竞争）

6. **iframe → 客户端运行时**(Bridge):`app.init{}`,表示"我挂好了,可以收数据"。
7. **客户端运行时** 收到 `app.init` 后才触发首屏(比如自动发一次 `list_orders`,或后端预置首帧)。
8. **后端 → 客户端运行时 → iframe**:`ui_update` 事件`{ payload.structuredContent }` → `done`。
9. **iframe**:`oneagent.data` 就绪,填充真实数据;SDK 开始采集 env 快照。

### 3.4 阶段 C1 — 用户点「批准 o2」（direct_action，不经 AI）

10. **iframe**:`oneagent.directAction('approve_order', { orderId:'o2' })`。
11. **客户端运行时 → 后端**:POST `app.call`,**路由到 Sandbox Runtime,不进 Agent/Model**。
12. **Sandbox** 执行 `mutate.py`,产出结果(可多帧流式)。
13. **后端 → iframe**:`ui_update` 事件 → `onData` 更新 widget,随后 `done` → `onDone`。
14. **旁路**:Sandbox/客户端运行时 写一条 `app.action` 进历史(store),供**后续 agent 读回**;这条**不回推 iframe**。

### 3.5 阶段 C2 — 用户点「AI 分析风险」（agent_action，经 AI，走方案 B）

15. **iframe**:`oneagent.agentAction('分析这些订单风险', { focus:['o1','o2','o3'] })`。
16. **客户端运行时**:采集**最新 env 快照**(latest-wins)→ POST `app.agent { intent, focus, env }`。
17. **后端**:建 `run(runId)`,**开一条下行流(SSE)**;从 store load 上下文 + env。
18. **Agent ReAct loop**(边想边推**同一条事件流**,消费方按 `type` 分发):
    - 思考 → `thinking` 事件 → Chat 面(skill 自定义呈现)
    - 调 `risk_score` → `tool_call` / `tool_result` 事件(**默认不改 widget**)
    - 脚本**显式 emit** → `ui_update` 事件(**更新 widget**)
    - 产出结论 → `text` 事件
19. **run 结束**:`done{status:success}`(RUN_FINISHED)→ **后端关流**,释放 run 临时状态,上下文 write-back store。
20. (可选)用户中途取消 → 对 `runId` 发**独立 POST cancel** → 后端中断 + 关流。

### 3.6 阶段 D — 关闭 / 释放

- 用户关 widget → **客户端运行时 直接销毁 iframe**(不通知 agent)。
- sandbox 回收 → 后端推 `app.control{sandbox_closed}` → **客户端运行时 静默销毁**。

### 3.7 全景图

```text
用户    iframe/Widget        客户端              Agent(ReAct)      Sandbox Runtime     Store
 │  点入口   │                 │                    │                  │              │
 │──────────┼────load_app────▶│───────────────────┼─────────────────▶│  建 appSession│
 │          │                 │◀──app.resource─────┼──────────────────│              │
 │          │◀─挂iframe/注SDK──│                    │                  │              │
 │          │──app.init(ready)▶│                    │                  │              │
 │          │◀──首屏 ui_update+done─────────────────┼──────────────────│              │
 │ 看到首屏  │                 │                    │                  │              │
 │          │                 │                    │                  │              │
 │ 批准o2   │─directAction───▶│──POST app.call─────┼─────────────────▶│ 执行 mutate  │
 │(不经AI)  │◀──ui_update + done───────────────────┼──────────────────│──写app.action▶│
 │          │                 │                    │                  │              │
 │ AI分析   │─agentAction────▶│─POST app.agent─────▶│  建run+开流       │              │
 │(经AI)    │                 │  (intent+env)      │──load上下文───────┼─────────────▶│
 │          │◀═事件流:thinking/tool_call/tool_result/text══│(叙事→Chat面) │              │
 │          │◀═事件流:ui_update════════════════════│◀─emit────────────│ 执行脚本      │
 │          │                 │◀──done+关流─────────│  释放run+写回──────┼─────────────▶│
```

> 图中「客户端」= **客户端运行时 (Client Runtime)**,见 §3.1。

三条主线概括:

- **入口/挂载**:客户端运行时 管(load_app → 挂 iframe → app.init 握手 → 首屏)。
- **不经 AI 的操作**:iframe → 客户端运行时 → **Sandbox** 直连,结果回推 + 旁路写历史。
- **经 AI 的操作**:iframe → 客户端运行时 → **Agent**,开一条 per-run 流边推边渲染,结束关流。

---

# Part 1 · Skill App 包规范

Skill App 是可发布的应用包,目录遵循 Anthropic Agent Skills 开放标准:根目录 `SKILL.md` + `scripts/` + `references/` + `assets/`;app-skill 自定义内容(`app.yaml`、`ui/` 等)统一收纳在 `assets/` 下。

## 1.1 目录结构

```text
my-app-skill/
├── SKILL.md                 # (标准) Agent 可读:用途、脚本说明、使用指引
├── scripts/                 # (标准) 业务脚本/cli,供 UI 与 Agent 调用
│   ├── query.py
│   └── mutate.py
├── references/              # (标准) 可选,供 Agent 检索的参考资料
└── assets/                  # (标准) 静态资源;App Skill 自定义内容放这里
    ├── app.yaml             # 客户端运行时 可读:结构化元信息(Agent 不感知)
    ├── ui/
    │   ├── index.html       # UI 入口(必选)
    │   ├── static/          # UI 静态子资源
    │   └── manifest.json    # 资源清单(推荐)
    └── schema/              # 可选,用户维度数据表
```

- 与标准一致:`SKILL.md`、`scripts/`、`references/`、`assets/`。
- App Skill 扩展:`assets/app.yaml`、`assets/ui/`、`assets/schema/`。
- 路径基准:`app.yaml` 内所有路径相对 **skill 根目录**。

## 1.2 SKILL.md

供 Agent 感知的说明文档(Agent Skills 标准入口):描述用途、适用场景、脚本调用顺序建议。Agent 不读取 `assets/app.yaml`,仅通过 SKILL.md + 运行时脚本描述感知 App。

## 1.3 assets/app.yaml

```yaml
id: order-review
name: Order Review
version: v1.0
description: 订单审核 App

entry:
  ui: assets/ui/index.html

resources:
  ui:
    index: assets/ui/index.html
    mimeType: text/html;profile=app-skill    # 一期:去 MCP 化,自有 profile
    manifest: assets/ui/manifest.json

scripts:
  - name: list_orders
    path: scripts/query.py
    visibility: [agent, ui]      # agent 可调 / ui 可通过 direct_action 调
  - name: approve_order
    path: scripts/mutate.py
    visibility: [agent, ui]
```

`scripts[].visibility` 取值:

- `agent`:Agent(ReAct loop)可调用。
- `ui`:Widget 可通过 `direct_action` 直接调用(不经 Model)。

> 二期会在此基础上为 `scripts[]` 增加 `input_schema` / `authz` 等安全字段(见 Part 3),第一期不定义。

---

# Part 2 · 运行时通信协议

## §1 传输与通信模型

### 1.1 两跳链路

- **iframe ↔ 客户端运行时(Bridge)**:JSON-RPC 2.0 over `postMessage`。
- **客户端运行时 ↔ 后端**:传输无关。协议只约束语义——**上行是请求,下行是流**。第一期推荐实现即下面的**方案 B**。

### 1.2 传输模型（方案 B:上行请求 + 下行 per-run 流 + run 结束关流）

不常开一条双向长连接,而是**把连接生命周期绑定到 run**:一次 `agent_action` 开一条下行流,run 结束就关流。这样"何时释放内存"毫无歧义——流一关,该 run 的临时状态全部释放。

| 环节 | 形态 | 说明 |
|---|---|---|
| **上行触发** | 普通请求(POST) | `direct_action` / `agent_action` 的发起;body 小、处理快、不占长时资源。`env` 快照随请求带上(§5) |
| **下行产出** | per-run 流(SSE 或 WS 读方向) | `agent_action` 发起后开一条流,持续 push `app.event`(事件流,见 §4),直到 `done` |
| **run 结束** | 关流 + 释放 | `done{status:success}` / `RUN_FINISHED` / `cancel` / `error` → 关流,释放该 run 的迭代器/句柄/缓冲,上下文写回 store |

**一次 `agent_action` 的完整时序**:

```text
iframe ──agentAction──▶ 客户端运行时 ──POST(intent + env)──▶ 后端
                                        后端建 run(runId),开下行流(SSE)
后端 ──stream: app.event 多帧(thinking / tool_call / ui_update / text …)──▶ 客户端运行时 ──▶ iframe
  ...
后端 ──stream: done{status:success}(RUN_FINISHED)──▶ 关闭流
                             (run 临时状态释放,上下文写回 store)
```

**控制与取消(方案 B 下无需常开反向通道)**:

| 控制 | 实现 | 备注 |
|---|---|---|
| `cancel` | 对 `runId` 发**独立请求**(POST) | 不需要一条常开的反向通道;后端收到即中断 run 并关流 |
| `sandbox_closed` | 后端在对应下行流内推一帧 `app.control{ type: "sandbox_closed" }`;若无活跃流,则由下次请求响应带出 | 客户端运行时 收到即静默释放(§6) |
| `direct_action` 结果 | 请求-响应(可为短 SSE),结束即关 | 多数一问一答,不常开流 |

> 断线重连 / `heartbeat` / `resync` 属二期(见 Part 3),第一期不引入。
>
> **内存基线**:连接短命(随 run 释放)+ 上下文不常驻连接(放 store,按需 load)+ run 结束强制 cleanup,是防 OOM 的三条硬约束,详见附录 D。

### 1.3 前端接入方式

**方式一:`oneagent` 全局封装(推荐)** —— 把"数据接收"与"主动调用"统一成友好 API,UI 无需直接碰 `postMessage`。

```js
// ① 首屏数据:全局直读(SDK 在 app.init 握手后注入)
renderBody(oneagent.data?.structuredContent);

// ② 界面事件:ui_update → 更新 widget(见 §4)
oneagent.onUiUpdate((e) => renderBody(e.payload.structuredContent));

// ③ 叙事事件(trajectory 合集):呈现完全由 skill UI 决定(见 §4.4)
oneagent.onTrajectory((e) => {
  // e.type ∈ thinking | text | tool_call | tool_result
  renderTrajectory(e);
});

// ④ direct_action:不经 AI,直连脚本/cli;返回一条事件流(ui_update* → done),用回调
oneagent.directAction('list_orders', { status: 'pending' }, {
  onData: (e) => renderBody(e.payload.structuredContent),   // ui_update,可多次
  onDone: (e) => markComplete(e),                            // done
  onError: (err) => showError(err),
});

// ⑤ agent_action:交给 agent 推理;只传意图 + 可选 focus,UI 现状由 env 自动带(见 §3.2/§5)
oneagent.agentAction('分析这些订单风险', { focus: ['o1', 'o2'] });
```

**方式二:原生 app-skill Bridge** —— 直接收发底层 `postMessage`(JSON-RPC 2.0),`oneagent` 即对它的封装。上行用 `app.call`(direct)/ `app.agent`(agent),下行监听 `app.notify`。

---

## §2 UI 资源下发 + 最小握手

### 2.1 资源与数据分离

`app.resource` **只下发 UI 资源本身,不含业务数据**。首屏与后续数据一律走 §4 的事件流(`ui_update`)。iframe 可先渲染骨架,再填充数据。

### 2.2 Payload（`data_type = app.resource`）

```json
{
  "data_type": "app.resource",
  "data": {
    "appSession": "sess_1a2b3c4d",
    "app": { "id": "order-review", "name": "Order Review", "version": "1.0.0" },
    "resource": {
      "uri": "app://order-review/assets/ui/index.html?v=1.0.0",
      "mimeType": "text/html;profile=app-skill",
      "manifest": { "version": "1.0.0", "entry": "index.html", "assets": [] }
    }
  }
}
```

### 2.3 最小握手 `app.init`（消除首帧竞争）

第一期用一个最小握手解决"iframe 还没挂好、首帧数据就到了"的时序竞争:

```text
客户端运行时 挂载 iframe → 载入 app.resource
iframe 就绪 ──(Bridge)──▶ app.init { }        // ready 信号,仅表示"我可以收数据了"
客户端运行时 收到 app.init ──▶ 下发首屏 ui_update 事件   // 首帧在 ready 之后才发,不会丢
```

- `app.init` 第一期**只承载 ready 语义**,不带参数。
- **协议版本号 / 能力协商属二期**(见 Part 3),第一期不引入。

---

## §3 UI → Agent 上行协议

上行两类:

| 类型 | Bridge 方法 | 后端路由 | 经 Model | 封装 API |
|---|---|---|---|---|
| **direct_action** | `app.call` | **Sandbox Runtime(直连执行)** | ❌ | `oneagent.directAction()` |
| **agent_action** | `app.agent` | **Agent(ReAct Loop)** | ✅ | `oneagent.agentAction()` |

纯本地交互(Tab 切换、展开折叠、本地筛选、表单输入)由 Widget 内部处理,不产生协议消息。

### 3.1 direct_action（不经 Model，直连 Sandbox 执行）

用户触发原子动作(查询/保存/执行/刷新),只需调脚本/cli 取结果,不涉及推理。**关键:它不进 ReAct/Model,由 客户端运行时 路由到 Sandbox Runtime 直接执行。**

**iframe → 客户端运行时**:`oneagent.directAction(name, args, callbacks)`,无需传 `appSession`(客户端运行时 按发起 iframe 补齐)。

**客户端运行时 → Sandbox Runtime(直连,不经 Agent messages)**:

```json
{
  "type": "app.call",
  "appSession": "sess_1a2b3c4d",
  "requestId": "req_001",
  "name": "list_orders",
  "arguments": { "status": "pending", "page": 1 }
}
```

执行结果通过 §4 的事件流(`ui_update*` → `done`)回到发起的 iframe。

### 3.2 交互历史归属（direct_action 也要能被后续 AI 读回）

> **不变量:一切用户交互(含不经 Model 的 direct_action)都必须可被后续 agent 读回。**

direct_action 虽不进 Model,但执行后 Sandbox Runtime / 客户端运行时 **旁路 append 一条最小记录到会话历史**,使下一轮 agent 推理时能看到"用户刚做了什么":

```json
{
  "type": "app.action",
  "appSession": "sess_1a2b3c4d",
  "actionType": "direct_action",
  "name": "approve_order",
  "arguments": { "orderId": "o2" },
  "resultSummary": "approved o2",
  "ts": 1780000000
}
```

- 只记**最小摘要**(名称、关键入参、结果摘要),不塞全量 `structuredContent`,避免历史膨胀。
- 该记录进会话历史/上下文,不回推给 iframe(iframe 已经通过 `ui_update` 事件拿到结果)。

### 3.3 agent_action（经 Model；只带意图 + 可选 focus）

用户触发开放性动作(需 agent 分析/规划/跨 App)。**payload 只带自然语言意图 + 可选 `focus` 提示;当前 UI 现状不在这里重复携带,而是统一由 §5 的 env 提供(latest-wins)。**

**iframe → 客户端运行时**:

```js
await oneagent.agentAction('分析这些订单风险', { focus: ['o1', 'o2', 'o3'] });
```

**客户端运行时 → Agent(`TEXT` 意图 + 可选 `GUI_ACTION` focus)**:

```json
{
  "stream": true,
  "messages": [{
    "role": "user",
    "part": [
      { "type": "TEXT", "text": { "content": "分析这些订单风险" } },
      { "type": "GUI_ACTION", "action_content": {
          "action_type": "agent_action",
          "action_timestamp": 1780000000,
          "action_payload": {
            "appSession": "sess_1a2b3c4d",
            "requestId": "msg_001",
            "focus": ["o1", "o2", "o3"]
          }
      } }
    ]
  }],
  "context": { "conversation_id": "conv_123", "user_id": "user_123" }
}
```

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `TEXT.text.content` | string | ✅ | 用户自然语言意图 |
| `action_type` | enum | ✅ | 固定 `agent_action` |
| `action_payload.focus` | any | ❌ | 可选焦点提示(如选中项);完整 UI 现状由 §5 env 提供 |
| `action_payload.requestId` | string | ✅ | 请求 ID,下行回填 |

---

## §4 Agent → UI 下行协议（统一事件流）

### 4.1 一个 action = 一条事件流

任何 action(不论走不走 AI)的响应都是**一条事件流**,流里是带 `type` 的事件,信封统一。**不再区分"result / trajectory 两条通道"**——它们只是同一条流里不同 `type` 的事件而已。

- `direct_action`(不走 AI)的流:`ui_update* → done`
- `agent_action`(走 AI)的流:`thinking* / tool_call / tool_result / ui_update* / text* → done`

> 纠正 V0.2:前端是**渲染目标**,不是"端工具"。agent 在 loop 里调脚本/cli 默认只产生 `tool_call` / `tool_result` 事件(叙事),**不会自动改 widget**;只有**显式 emit** 才产生 `ui_update` 事件改 widget。

### 4.2 事件信封（所有事件同构）

```json
{
  "type": "ui_update",
  "appSession": "sess_1a2b3c4d",
  "requestId": "req_001",
  "seq": 3,
  "ts": 1780000000,
  "payload": { "...": "..." }
}
```

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `type` | enum | ✅ | 事件类型(见 §4.3) |
| `appSession` | string | ✅ | 目标 App 实例,客户端运行时据此路由 iframe |
| `requestId` | string | ✅ | 关联发起的 action(direct/agent);同一 action 的所有事件共用 |
| `seq` | number | ✅ | 流内序号,同 requestId 递增,保证顺序 |
| `ts` | number | ❌ | 时间戳 |
| `payload` | object | ✅ | 类型相关内容(见 §4.3) |

### 4.3 事件类型（第一期）

| type | 分组 | payload | 说明 |
|---|---|---|---|
| `thinking` | 叙事 | `{ delta, final }` | 思考增量;建议 skill UI 折叠展示,默认可不持久化 |
| `text` | 叙事 | `{ delta, final }` | 正文增量 |
| `tool_call` | 叙事 | `{ callId, name, arguments }` | agent 调了某工具(默认一张卡片,skill 自定义样式) |
| `tool_result` | 叙事 | `{ callId, name, resultSummary }` | 该工具的结果摘要 |
| `ui_update` | 界面 | `{ structuredContent, _meta? }` | **widget 数据变更**(第一期全量覆盖,不做 patch) |
| `done` | 收尾 | `{ status: "success"\|"error", error? }` | 标记该 action 的事件流结束 |

- 叙事类(`thinking`/`text`/`tool_call`/`tool_result`)**统称 trajectory**——只是这几类事件的合称,不是独立 `type`。复用现有 `ContentBlock` 词汇(`common/agent_framework/user_interface/content_blocks.py`)。
- `ui_update.payload.structuredContent`:**全量**业务数据(Model 可见);`_meta`:Widget 专用,Model 不可见。

### 4.4 路由到两个呈现面（消费方按 type 分发）

"两个呈现面"不再是协议里的两条通道,而是**消费方按 `type` 决定去哪**:

| 事件 type | 去哪 | 呈现 |
|---|---|---|
| `ui_update` | 更新 widget(App 面) | 由 skill UI 用 `structuredContent` 覆盖渲染 |
| `thinking` / `text` / `tool_call` / `tool_result` | Chat 面 | **由 skill UI 自定义**(折叠、卡片样式等) |
| `done` | 收尾 | 关流 / 标记完成;`status=error` 时展示错误、保留现有 widget 状态 |

前端消费:

```js
// 界面事件:更新 widget
oneagent.onUiUpdate((e) => renderBody(e.payload.structuredContent));

// 叙事事件(trajectory 合集):Chat 面,呈现完全由 skill UI 决定
oneagent.onTrajectory((e) => {
  switch (e.type) {
    case 'thinking':    appendThinking(e.payload.delta); break;
    case 'text':        appendAnswer(e.payload.delta);   break;
    case 'tool_call':   renderToolCard(e.payload);       break;
    case 'tool_result': updateToolCard(e.payload);       break;
  }
});
```

> `onTrajectory` 只是"订阅那 4 类叙事事件"的便捷封装;`ui_update` 走 `onUiUpdate`。`direct_action` 的 `onData` / `onDone`(§1.3)本质就是订阅它那条流的 `ui_update` / `done`。
> **客户端运行时 fallback**:skill UI 未订阅叙事事件时,客户端运行时可用默认样式在对话区渲染它们。

### 4.5 ui_update:显式 emit + 全量覆盖

要改 widget,脚本必须**显式 emit**(agent 内部 tool_call 默认不改 widget):

- 脚本输出标记 `visible: true`,或调用专用 `app_emit` cli;
- Sandbox Runtime 捕获被标记的输出 → 转成一个 `ui_update` 事件推入流;
- 同一 `requestId` 可有多个 `ui_update` 事件,最后由 `done` 收尾。

> 第一期 `ui_update` 每次**全量覆盖** `structuredContent`,**不引入 `patch` / `stateVersion`**——增量与断线一致性属二期(见 Part 3)。

### 4.6 可见性

| 字段 | Model | Widget | Transcript |
|---|---|---|---|
| `ui_update.payload.structuredContent` | ✅ | ✅ | ✅ |
| `thinking` / `text` / `tool_call` / `tool_result` | ✅ | ✅ | ✅(thinking 可不持久化) |
| `ui_update.payload._meta` | ❌ | ✅ | ❌ |

---

## §5 UI 现状作 env

### 5.1 语义

客户端运行时 维护当前 Widget 的**最新 UI 快照**;向 Agent 发起推理时,把该快照作为 **env 上下文**打包进 Model 上下文,让 agent 始终知道"用户此刻在看什么、在做什么"。

- **latest-wins**:只保留最新一份,旧快照不进历史(避免 context 被过时快照塞爆、避免 agent 分不清"现在")。
- **语义投影**:下发的是投影后的语义摘要,不是原始 DOM/组件 state。
- **刷新边界**:env 快照按**用户交互边界**刷新(用户操作 UI 时更新),**而非每个 ReAct step**——一次 agent loop 内用户不操作、UI 不变,快照保持稳定,避免无谓重发。

### 5.2 快照采集约定（SDK 默认 + App 可覆盖）

```js
// SDK 默认采集:视图、筛选、选中、可见项、滚动位置等
oneagent.snapshot();

// App 可注册自定义投影(把内部 state 投影成"用户在做什么"的语义摘要)
oneagent.registerSnapshot(() => ({
  view: currentView,
  summary: `用户在订单列表,筛选 pending,选中 ${selected.length} 条`,
  selected,
}));
```

### 5.3 载体

客户端运行时 在向 Agent 发起每轮推理时,附一段 `env`(latest-wins 快照)。app-skill 侧用 `context.env.ui_snapshot` 承载(或专门的 `GUI_ENV` part)。

> `agent_action` 不再单独携带 `ui_snapshot`(V0.2 的做法会重复下发);UI 现状统一走这里。agent_action 里的 `focus` 只是"这次特别关注什么"的轻提示。

---

## §6 App 生命周期（静默释放）

- **`load_app(appId)`**:加载 App → 注册脚本与资源 → 下发 `app.resource` 挂载 Widget。多 App 可多次调用。
- **静默释放**:**不设显式 `requestClose` / `unload_app` 交互**。Widget 生命周期**绑定 sandbox**:
  - sandbox 被回收 → 后端在下行流内推一帧 `app.control{sandbox_closed}`(无活跃流则由下次请求响应带出) → 客户端运行时 静默销毁对应 iframe,并从 Agent 上下文移除;
  - 用户手动关闭 widget → 客户端运行时 侧直接销毁 iframe 即可,无需通知 agent(sandbox 复用时下次 load 重建)。

> 结论:sandbox 没了,widget 就没了。生命周期不需要一套额外的关闭协议。

---

# Part 3 · 二期方向（仅列方向，本期不定义）

以下能力第一期**只登记、不定义**,以便实现聚焦 MVP。等核心闭环跑通后再展开设计。

| 方向 | 说明 | 关联问题 |
|---|---|---|
| **安全护栏** | `direct_action` 绕过 AI,是最危险路径。二期定义:`scripts[]` 的 `input_schema`(JSON Schema 校验)+ `authz`(按用户角色鉴权,如谁能 `approve_order`)+ 限流;`visibility:[ui]` 只是白名单前提 | #4 |
| **状态一致性 + 增量** | `ui_update` 增加 `stateVersion`(appSession 级单调递增);`patch`(RFC6902 增量)挂在版本基线上,替代全量覆盖以省带宽 | #2 |
| **断线续传** | 重连时 client 上报 last `stateVersion` → 后端先回全量快照重同步再续增量;`control: resync`;in-flight loop 掉线处理 | #2 |
| **深度能力协商** | `app.init` 增加 `protocolVersion` + capabilities 双向协商 | #7 |
| **客户端环境上下文** | 客户端运行时向 iframe 注入主题(暗/亮)、语言等(与 UI 快照无关的宿主环境) | — |

**明确移出协议范畴(不做)**:

| 方向 | 处理 |
|---|---|
| iframe 高度自适应 / inline·pip·fullscreen | 不在协议范畴,由客户端运行时自行实现 |

---

## §7 Demo 简化说明

参考实现(demo)阶段**可不接真实 agent server 与 tool proxy**:

- 客户端运行时 直接在本地跑一个"伪 ReAct loop":收到 `agent_action` 后,顺序执行本地 cli/脚本,把显式 emit 的结果作为 `ui_update` 事件、把叙事作为 `thinking`/`text`/`tool_call`/`tool_result` 事件推给 iframe,末尾 `done`;`direct_action` 直接本地执行并回 `ui_update* → done`。
- 这样即可完整演示"统一事件流 + 按 type 分发到两个呈现面 + UI 快照 env + direct/agent 双路径 + 历史归属",而不必搭 `work_agent_server`。
- 后续把"伪 loop"替换为真实 Agent / Sandbox,事件协议不变。

---

## 附录 A：下行消息与事件汇总

下行分两类:**挂载消息**(`app.resource`)和**事件流**(`app.event`,一次 action 的响应)。

| 消息/事件 | 方向 | 用途 |
|---|---|---|
| `app.resource` | 后端 → 客户端 | UI 挂载(仅资源,不含数据) |
| `app.event` | 后端 → Widget | **一次 action 的事件流**,信封见 §4.2 |
| `app.action` | 旁路写入会话历史 | direct_action 的最小交互记录(供后续 agent 读回) |

`app.event.type` 取值(第一期):

| type | 分组 | 用途 |
|---|---|---|
| `thinking` / `text` / `tool_call` / `tool_result` | 叙事(统称 trajectory) | Chat 面呈现(skill 自定义) |
| `ui_update` | 界面 | 更新 widget 数据(全量) |
| `done` | 收尾 | 标记该 action 事件流结束(`status` success/error) |

## 附录 B：命名约定

| 概念 | 命名 | 示例 |
|---|---|---|
| 不经 AI 的动作 | `direct_action` | `oneagent.directAction('list_orders', …)` |
| 经 AI 的动作 | `agent_action` | `oneagent.agentAction('分析风险', { focus })` |
| 下行事件(统一信封) | `app.event` | `{ type, appSession, requestId, seq, payload }` |
| 界面变更事件 | `ui_update` | `oneagent.onUiUpdate(cb)` |
| 叙事事件(合称) | `trajectory` | `thinking`/`text`/`tool_call`/`tool_result`;`oneagent.onTrajectory(cb)` |
| 事件流收尾 | `done` | `{ status: 'success' \| 'error' }` |
| App 实例 ID | `appSession` | `sess_1a2b3c4d` |
| 请求关联 ID | `requestId` | `req_001` |
| run(一次 agent 任务)ID | `runId` | `run_001`(cancel 的目标,见 §1.2) |
| 流式序号 | `seq` | `1, 2, 3 …` |
| 脚本全名 | `{appId}.{name}` | `order-review.list_orders` |
| Resource URI | `app://{appId}/{path}?v={version}` | `app://order-review/assets/ui/index.html?v=1.0.0` |
| UI 资源 MIME | `text/html;profile=app-skill` | — |

## 附录 C：Bridge ↔ app-skill 映射

上行(iframe → 客户端运行时 → 后端):

| Bridge 方法 | 后端路由 | 用途 | 封装 API |
|---|---|---|---|
| `app.call` | Sandbox Runtime(不经 Model) | 调脚本/cli | `oneagent.directAction()` |
| `app.agent` | Agent ReAct(经 Model) | 触发推理(只带意图 + focus) | `oneagent.agentAction()` |
| `app.init` | 客户端运行时 | iframe 就绪信号 → 触发首帧 | (SDK 自动) |
| (每次触发随请求带) | `context.env.ui_snapshot` | UI 现状作 env | `oneagent.snapshot()` |

下行(后端 → 客户端运行时 → iframe,均可流式):

| app-skill 下行 | Bridge 形态 | 用途 | 封装接收 |
|---|---|---|---|
| `app.resource` | 加载 iframe | UI 挂载 | — |
| `app.event{type:ui_update}` | `app.notify`(事件流) | 更新 widget | `oneagent.onUiUpdate()` / direct 的 `onData` |
| `app.event{type:thinking/text/tool_call/tool_result}` | `app.notify`(事件流) | Chat 面叙事(trajectory) | `oneagent.onTrajectory()` |
| `app.event{type:done}` | `app.notify` | action 事件流收尾 | direct 的 `onDone` |
| `app.control{sandbox_closed}`(下行流内) | 客户端运行时 静默销毁 iframe | 静默释放 | — |

取消(方案 B):`cancel` 不走下行流,而是对 `runId` 发独立请求(见 §1.2)。

## 附录 D：内存与连接（方案 B 的防 OOM 约束）

长连接本身几乎不吃内存(一条空闲流仅 socket 缓冲 + 少量连接态);真正把内存打满的是"**连接上挂了多少常驻状态**"。方案 B 通过"连接生命周期 = run 生命周期"让释放时机毫无歧义,再叠加以下硬约束:

| 约束 | 做法 |
|---|---|
| **上下文不常驻连接** | 消息历史 / env / 结构化数据放 store(Redis/DB),run 时按需 load,不挂在连接对象上 |
| **run 结束强制释放** | `RUN_FINISHED` / `cancel` / `error` 走同一套 cleanup:关流 + 释放迭代器/句柄/缓冲 |
| **背压 + 上限** | 下行有缓冲上限;慢消费者(iframe 卡住)触发丢弃旧帧或直接断流,不无限堆积 |
| **闲置超时 + 连接配额** | 每用户 / 每 sandbox 限连接数,空闲 N 秒回收 |
| **绑定 sandbox 生命周期** | sandbox 回收 → 连带关流、清 run(复用 §6 的 `sandbox_closed`) |

> 直觉验证:内存占用 ≈ 并发 **活跃 run 数** × 单 run 临时状态,而**不是**历史累计连接数。空闲/已结束的 run 不占内存。
