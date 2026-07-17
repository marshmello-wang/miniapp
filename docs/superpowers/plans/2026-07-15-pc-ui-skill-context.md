# PC UI Skill 统一上下文 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 PC 端 Chat 与 Skill UI 重构为单一 Conversation、单一 Agent、Conversation SSE 事件流，并引入双层 Snapshot 与 Direct Relay。

**Architecture:** 新增 `ConversationRuntime` 作为确定性协调层；Command 走 HTTP POST，Durable Events 走 Conversation SSE；Agent Worker 统一 Chat/UI Agent Action；Direct Relay 复用 Sandbox + NDJSON；Context Projector 由 Skill 拥有。

**Tech Stack:** Python 3 / FastAPI / asyncio / SQLite(MessageStore 扩展) / React / TypeScript / Vitest / pytest

## Global Constraints

- 一个 Conversation 只有一个 Agent；UI 不是 Agent。
- `load_skill` 不自动打开 UI；AI 文本进 Chat，AI UI 内容必须经 Skill UI CLI。
- Direct Action 记录但不进模型 Context，不唤醒 Agent。
- Agent Action 出队时采集 View Snapshot，Skill `context_snapshot` 生成 Business Context 后进模型。
- 用户 intent 为原始 User Message，无 `[USER_INTENT]` 包裹；无 UI 时不注入空 Runtime Context。
- UI Agent Action 排队期间 UI loading 且禁止 Direct Action；Agent Lane per-conversation FIFO。
- 业务 DB 按 `user × skill` 持久化；Conversation 状态隔离。
- 不要求兼容 app-skill v0.3 wire protocol。

---

## File Map

| File | Responsibility |
|------|----------------|
| `backend/conversations/models.py` | Action/Event/UIInstance dataclasses |
| `backend/conversations/event_store.py` | Durable event append + replay |
| `backend/conversations/protocol.py` | Envelope validation, event factory |
| `backend/conversations/agent_lane.py` | Per-conversation FIFO queue |
| `backend/conversations/direct_relay.py` | Generic direct action forwarding |
| `backend/conversations/context_builder.py` | View snapshot + projector + turn context |
| `backend/conversations/runtime.py` | Orchestration, SSE broadcast, commit gate |
| `backend/conversations/agent_worker.py` | Unified agent execution |
| `backend/routers/conversations_router.py` | POST actions/snapshot/cancel + GET SSE |
| `frontend/src/conversations/eventStream.ts` | Conversation SSE client |
| `frontend/src/conversations/types.ts` | Protocol types |
| `frontend/src/host/conversationBridge.ts` | Replaces per-action bridge |

---

### Task 1: Conversation Event Store

**Files:**
- Create: `miniapp_demo/backend/conversations/__init__.py`
- Create: `miniapp_demo/backend/conversations/models.py`
- Create: `miniapp_demo/backend/conversations/event_store.py`
- Create: `miniapp_demo/backend/conversations/protocol.py`
- Create: `miniapp_demo/backend/tests/test_conversation_event_store.py`

**Interfaces:**
- Produces: `EventStore.append(event) -> int` (returns conversationSeq)
- Produces: `EventStore.replay(conversation_id, after=0) -> list[DurableEvent]`
- Produces: `make_durable_event(...) -> dict`

- [ ] **Step 1: Write failing tests** for append monotonic seq, replay after cursor, eventId dedup metadata
- [ ] **Step 2: Run** `python -m pytest miniapp_demo/backend/tests/test_conversation_event_store.py -v` → FAIL
- [ ] **Step 3: Implement** SQLite-backed event store under `~/.miniapp/conversations/{id}/events.db`
- [ ] **Step 4: Run tests** → PASS
- [ ] **Step 5: Commit**

---

### Task 2: Agent Lane + Action Idempotency

**Files:**
- Create: `miniapp_demo/backend/conversations/agent_lane.py`
- Create: `miniapp_demo/backend/tests/test_agent_lane.py`

**Interfaces:**
- Consumes: `EventStore.append`
- Produces: `AgentLane.enqueue(action) -> position`
- Produces: `AgentLane.dequeue() -> Action | None`
- Produces: `ActionRegistry.register(action_id) -> accepted|duplicate`

- [ ] **Step 1: Write failing tests** for FIFO, duplicate actionId, cancel queued
- [ ] **Step 2-4: Implement + verify**
- [ ] **Step 5: Commit**

---

### Task 3: Conversation Router + SSE

**Files:**
- Create: `miniapp_demo/backend/routers/conversations_router.py`
- Modify: `miniapp_demo/backend/main.py`
- Create: `miniapp_demo/backend/tests/test_conversations_router.py`

**Interfaces:**
- `POST /api/conversations/{id}/actions`
- `GET /api/conversations/{id}/events?after=N`
- `POST /api/conversations/{id}/actions/{actionId}/snapshot`
- `POST /api/conversations/{id}/actions/{actionId}/cancel`

- [ ] **Step 1: Write failing integration tests** for SSE replay and action accepted event
- [ ] **Step 2-4: Implement minimal runtime stub wired to EventStore + AgentLane**
- [ ] **Step 5: Commit**

---

### Task 4: Direct Relay

**Files:**
- Create: `miniapp_demo/backend/conversations/direct_relay.py`
- Modify: `miniapp_demo/backend/app_registry.py` (add context_snapshot script ref)
- Create: `miniapp_demo/backend/tests/test_direct_relay.py`

**Interfaces:**
- Consumes: `sandbox.run_script`, `app_registry.get_app`
- Produces: `DirectRelay.execute(action) -> list[ui_command]`

- [ ] **Step 1: Write failing tests** for manifest resolution, revision reject, no agent dispatch
- [ ] **Step 2-4: Implement** by extracting logic from `engine.direct_action`
- [ ] **Step 5: Commit**

---

### Task 5: Context Builder + Snapshot Flow

**Files:**
- Create: `miniapp_demo/backend/conversations/context_builder.py`
- Create: `miniapp_demo/backend/tests/test_context_builder.py`

**Interfaces:**
- Consumes: View snapshot POST body, Skill `context_snapshot` script
- Produces: `build_turn_context(conversation_id, action, business_context) -> messages`

- [ ] **Step 1: Write failing tests** for no-UI (omit context block), with-UI YAML block, raw user intent
- [ ] **Step 2-4: Implement** projector invocation via sandbox
- [ ] **Step 5: Commit**

---

### Task 6: Unified Agent Worker

**Files:**
- Create: `miniapp_demo/backend/conversations/agent_worker.py`
- Modify: `miniapp_demo/backend/chat_agent_runner.py` (extract shared runner)
- Delete path: `MiniAppEngine.agent_action` usage from runtime

**Interfaces:**
- Produces: async generator of agent events → durable conversation events

- [ ] **Step 1: Write failing tests** for load_skill without ui.open, text vs ui_command routing
- [ ] **Step 2-4: Implement** single worker using existing react agent + load_skill
- [ ] **Step 5: Commit**

---

### Task 7: Conversation Runtime Orchestration

**Files:**
- Create: `miniapp_demo/backend/conversations/runtime.py`
- Modify: `miniapp_demo/backend/routers/conversations_router.py`

- [ ] Wire Agent Lane dequeue → snapshot.requested → snapshot POST → context → agent worker
- [ ] Wire Direct Relay with UI lock during UI agent action queue/run
- [ ] Commit gate with expectedRevision
- [ ] Tests for concurrent chat agent + direct action stale revision

---

### Task 8: Frontend Conversation SSE Client

**Files:**
- Create: `miniapp_demo/frontend/src/conversations/types.ts`
- Create: `miniapp_demo/frontend/src/conversations/eventStream.ts`
- Create: `miniapp_demo/frontend/src/conversations/actionClient.ts`

- [ ] Subscribe SSE on ChatPage mount
- [ ] POST actions instead of old runtime/actions
- [ ] Handle ui.snapshot.requested → getEnv → POST snapshot

---

### Task 9: Host Bridge Refactor

**Files:**
- Create: `miniapp_demo/frontend/src/host/conversationBridge.ts`
- Modify: `miniapp_demo/frontend/src/components/SkillPanel.tsx`
- Modify: `miniapp_demo/sdk/miniapp.js`

- [ ] Remove client-side env on agentAction submit
- [ ] React to ui.command events from SSE
- [ ] UI loading lock during agent action queue

---

### Task 10: Demo Skill Update

**Files:**
- Modify bundled app (e.g. `fortune-teller` or starter) with `context_snapshot` script + UI manifest routes

- [ ] End-to-end manual test: load skill → UI CLI open → chat + direct + agent queue

---

### Task 11: Remove Legacy v0.3 Path

**Files:**
- Modify: `miniapp_demo/backend/runtime_service.py`, `runtime_router.py`, `engine.py`, `chat_engine.py`
- Modify: frontend old transport files

- [ ] Delete or stub old per-action SSE once new path works
- [ ] Update tests

---

## Spec Coverage Self-Review

| Spec requirement | Task |
|------------------|------|
| Single Agent | 6, 7 |
| load_skill no auto UI | 6, 10 |
| Direct not in context | 4, 5 |
| Double snapshot | 5 |
| Agent Lane FIFO | 2, 7 |
| UI lock on queue | 7, 9 |
| Conversation SSE replay | 1, 3, 8 |
| Direct Relay generic | 4 |
| No USER_INTENT wrapper | 5 |
| No empty UI context | 5 |
| Revision commit gate | 7 |
| user×skill DB persistence | 4 (reuse stores.business_store_dir for skill) |
