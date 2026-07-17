# Conversation Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可持久化、可重放的 Conversation Event Stream，并打通第一条 Direct Action 纵切：Command POST → Generic Direct Relay → Sandbox → `ui.command` → Conversation SSE。

**Architecture:** 新增独立的 Conversation Runtime，不修改现有 Agent 行为。Command 与 Event Stream 分离：Action 使用 POST 提交，Durable Event 写入 SQLite Event Store，所有订阅者通过 Conversation 级 SSE 按 `conversationSeq` 重放和实时接收。Direct Relay 复用现有 Registry、Sandbox 和 NDJSON 安全边界，但不写模型历史。

**Tech Stack:** Python 3、FastAPI、asyncio、sqlite3、unittest、TypeScript、Fetch/ReadableStream、Vitest。

## Global Constraints

- 本计划只实现 Conversation/Event/SSE/Direct Action 基础纵切，不实现 Agent Lane、Snapshot、Context Projector 或页面切换。
- 不要求兼容 app-skill v0.3 wire protocol；实施期间旧路由可暂时并存，后续切换计划会删除。
- Direct Relay 不包含任何具体 Skill 业务逻辑，不构建 Context，不调度 Agent。
- Durable Event 的 `conversationSeq` 在单个 Conversation 内严格递增。
- Direct Action 写 Event Log，但不得调用 `stores.append_app_action` 或写 Agent MessageStore。
- Skill 持久目录按 `user × skill` 计算，不按 Conversation 计算。
- 结构化 UI 输出继续使用独享 NDJSON 结果文件，禁止解析 stdout。
- 新增代码使用现有依赖，不添加第三方包。
- 所有生产代码变更遵循 TDD：先红、再绿、最后回归。

---

## Scope Decomposition

完整设计分成三个可独立验收的实施计划：

1. **本计划：Conversation Runtime Foundation**
   - Durable Event Store
   - Conversation SSE + replay
   - Direct Relay
   - 前端传输客户端
2. **后续计划：Unified Agent and Context**
   - Agent Lane FIFO
   - 双层 Snapshot / Context Projector
   - 唯一 Agent Worker 与 dynamic `load_skill`
   - UI revision / Commit Gate
3. **后续计划：Host and UI Integration**
   - HostBridge / SDK / ChatPage 切换
   - UI loading/lock
   - `agent.text` 与 `ui.command` Surface 投影
   - 删除 v0.3 双 Agent 和旧传输

本计划完成后，系统具备无需 LLM 的首个可运行纵切，可独立部署和测试。

## File Structure

### Backend — create

- `miniapp_demo/backend/conversation_protocol.py`
  - 定义 Action、Durable Event、UI Command 的边界类型和校验函数。
- `miniapp_demo/backend/event_store.py`
  - SQLite 事件持久化、`conversationSeq` 分配、Action 幂等记录、replay。
- `miniapp_demo/backend/event_hub.py`
  - 进程内订阅唤醒；持久事实仍以 Event Store 为准。
- `miniapp_demo/backend/persistent_store.py`
  - 计算并初始化 `user × skill` 持久目录。
- `miniapp_demo/backend/direct_relay.py`
  - Generic Direct Relay；解析 Manifest 并调用 Sandbox。
- `miniapp_demo/backend/conversation_runtime.py`
  - 接收 Command、驱动 Direct Relay、写 Durable Events、提供订阅迭代器。
- `miniapp_demo/backend/routers/conversation_router.py`
  - Action POST 与 Conversation SSE HTTP API。
- `miniapp_demo/backend/tests/test_conversation_protocol.py`
- `miniapp_demo/backend/tests/test_event_store.py`
- `miniapp_demo/backend/tests/test_event_hub.py`
- `miniapp_demo/backend/tests/test_persistent_store.py`
- `miniapp_demo/backend/tests/test_direct_relay.py`
- `miniapp_demo/backend/tests/test_conversation_runtime.py`
- `miniapp_demo/backend/tests/test_conversation_router.py`

### Backend — modify

- `miniapp_demo/backend/config.py`
  - 新增 Conversation DB 和 `user × skill` store 根目录。
- `miniapp_demo/backend/script_metadata.py`
  - 接受标准 `ui_command` NDJSON event。
- `miniapp_demo/backend/sandbox.py`
  - 透传 `uiCommands` metadata，不改变进程隔离方式。
- `miniapp_demo/backend/main.py`
  - 注册 Conversation Router 并在 shutdown 关闭 Runtime。

### Frontend — create

- `miniapp_demo/frontend/src/types/conversation.ts`
  - Action、Durable Event、UI Command 类型。
- `miniapp_demo/frontend/src/transport/postAction.ts`
  - 提交 Command，接收 ACK。
- `miniapp_demo/frontend/src/transport/conversationStream.ts`
  - 订阅 Conversation SSE、校验顺序、支持 `after`。
- `miniapp_demo/frontend/src/types/conversation.test.ts`
- `miniapp_demo/frontend/src/transport/postAction.test.ts`
- `miniapp_demo/frontend/src/transport/conversationStream.test.ts`

### Existing files intentionally untouched

- `miniapp_demo/backend/chat_engine.py`
- `miniapp_demo/backend/engine.py`
- `miniapp_demo/backend/chat_agent_runner.py`
- `miniapp_demo/backend/agent_runner.py`
- `miniapp_demo/frontend/src/host/bridge.ts`
- `miniapp_demo/sdk/miniapp.js`
- `miniapp_demo/frontend/src/pages/ChatPage.tsx`

这些文件在后续两个计划中切换，避免本纵切把协议基础和 UI/Agent 迁移绑成一次大爆炸。

---

### Task 1: Define Conversation Protocol Types

**Files:**
- Create: `miniapp_demo/backend/conversation_protocol.py`
- Create: `miniapp_demo/backend/tests/test_conversation_protocol.py`

**Interfaces:**
- Produces: `ActionCommand.from_dict(raw) -> ActionCommand`
- Produces: `UiCommand.from_dict(raw) -> UiCommand`
- Produces: `DurableEvent.to_dict() -> dict[str, Any]`
- Consumes: only Python stdlib

- [ ] **Step 1: Write failing protocol validation tests**

```python
# miniapp_demo/backend/tests/test_conversation_protocol.py
import unittest

from miniapp_demo.backend.conversation_protocol import (
    ActionCommand,
    ProtocolValidationError,
    UiCommand,
)


class ConversationProtocolTest(unittest.TestCase):
    def test_parses_direct_action_without_agent_fields(self):
        command = ActionCommand.from_dict({
            "actionId": "act-1",
            "kind": "direct",
            "source": "ui",
            "skillId": "order-review",
            "uiInstanceId": "ui-1",
            "name": "approve",
            "args": {"orderId": "1042"},
            "expectedRevision": 7,
        })
        self.assertEqual("act-1", command.action_id)
        self.assertEqual("direct", command.kind)
        self.assertEqual({"orderId": "1042"}, command.args)

    def test_rejects_direct_action_without_skill_name_or_revision(self):
        base = {
            "actionId": "act-1",
            "kind": "direct",
            "source": "ui",
            "skillId": "order-review",
            "uiInstanceId": "ui-1",
            "name": "approve",
            "expectedRevision": 7,
        }
        for missing in ("skillId", "uiInstanceId", "name", "expectedRevision"):
            raw = dict(base)
            raw.pop(missing)
            with self.subTest(missing=missing):
                with self.assertRaises(ProtocolValidationError):
                    ActionCommand.from_dict(raw)

    def test_parses_ui_command_and_rejects_unknown_command(self):
        command = UiCommand.from_dict({
            "type": "ui_command",
            "command": "show_content",
            "route": "/result",
            "payload": {"message": "done"},
            "expectedRevision": 7,
        })
        self.assertEqual("show_content", command.command)
        self.assertEqual("/result", command.route)

        with self.assertRaises(ProtocolValidationError):
            UiCommand.from_dict({
                "type": "ui_command",
                "command": "execute_javascript",
                "payload": {},
                "expectedRevision": 7,
            })


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify red**

Run:

```bash
python3 -m unittest miniapp_demo.backend.tests.test_conversation_protocol -v
```

Expected: `ModuleNotFoundError: miniapp_demo.backend.conversation_protocol`.

- [ ] **Step 3: Implement immutable protocol dataclasses**

```python
# miniapp_demo/backend/conversation_protocol.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


class ProtocolValidationError(ValueError):
    pass


def _required_string(raw: Dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ProtocolValidationError(f"{key} must be a non-empty string")
    return value


@dataclass(frozen=True)
class ActionCommand:
    action_id: str
    kind: Literal["agent", "direct"]
    source: Literal["chat", "ui"]
    skill_id: Optional[str] = None
    ui_instance_id: Optional[str] = None
    intent: str = ""
    name: Optional[str] = None
    args: Dict[str, Any] = field(default_factory=dict)
    expected_revision: Optional[int] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ActionCommand":
        action_id = _required_string(raw, "actionId")
        kind = raw.get("kind")
        source = raw.get("source")
        if kind not in ("agent", "direct"):
            raise ProtocolValidationError("kind must be agent or direct")
        if source not in ("chat", "ui"):
            raise ProtocolValidationError("source must be chat or ui")
        skill_id = raw.get("skillId")
        ui_instance_id = raw.get("uiInstanceId")
        name = raw.get("name")
        expected_revision = raw.get("expectedRevision")
        if kind == "direct":
            skill_id = _required_string(raw, "skillId")
            ui_instance_id = _required_string(raw, "uiInstanceId")
            name = _required_string(raw, "name")
            if not isinstance(expected_revision, int) or expected_revision < 0:
                raise ProtocolValidationError(
                    "expectedRevision must be a non-negative integer"
                )
        args = raw.get("args", {})
        if not isinstance(args, dict):
            raise ProtocolValidationError("args must be an object")
        intent = raw.get("intent", "")
        if not isinstance(intent, str):
            raise ProtocolValidationError("intent must be a string")
        return cls(
            action_id=action_id,
            kind=kind,
            source=source,
            skill_id=skill_id,
            ui_instance_id=ui_instance_id,
            intent=intent,
            name=name,
            args=dict(args),
            expected_revision=expected_revision,
        )


@dataclass(frozen=True)
class UiCommand:
    command: Literal["open", "navigate", "show_content", "patch", "close"]
    payload: Dict[str, Any]
    expected_revision: int
    route: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "UiCommand":
        if raw.get("type") != "ui_command":
            raise ProtocolValidationError("type must be ui_command")
        command = raw.get("command")
        if command not in ("open", "navigate", "show_content", "patch", "close"):
            raise ProtocolValidationError("unsupported ui command")
        payload = raw.get("payload", {})
        revision = raw.get("expectedRevision")
        route = raw.get("route")
        if not isinstance(payload, dict):
            raise ProtocolValidationError("payload must be an object")
        if not isinstance(revision, int) or revision < 0:
            raise ProtocolValidationError(
                "expectedRevision must be a non-negative integer"
            )
        if route is not None and not isinstance(route, str):
            raise ProtocolValidationError("route must be a string")
        return cls(command, dict(payload), revision, route)


@dataclass(frozen=True)
class DurableEvent:
    event_id: str
    conversation_id: str
    conversation_seq: int
    actor: Literal["user", "agent", "tool", "runtime"]
    type: str
    ts: str
    payload: Dict[str, Any]
    action_id: Optional[str] = None
    skill_id: Optional[str] = None
    ui_instance_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eventId": self.event_id,
            "conversationId": self.conversation_id,
            "conversationSeq": self.conversation_seq,
            "actor": self.actor,
            "type": self.type,
            "ts": self.ts,
            "payload": self.payload,
            **({"actionId": self.action_id} if self.action_id else {}),
            **({"skillId": self.skill_id} if self.skill_id else {}),
            **({"uiInstanceId": self.ui_instance_id} if self.ui_instance_id else {}),
        }
```

- [ ] **Step 4: Run protocol tests**

Run:

```bash
python3 -m unittest miniapp_demo.backend.tests.test_conversation_protocol -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add miniapp_demo/backend/conversation_protocol.py miniapp_demo/backend/tests/test_conversation_protocol.py
git commit -m "feat: define conversation command and event protocol"
```

---

### Task 2: Add Durable SQLite Event Store

**Files:**
- Modify: `miniapp_demo/backend/config.py:17-21,88-92`
- Create: `miniapp_demo/backend/event_store.py`
- Create: `miniapp_demo/backend/tests/test_event_store.py`

**Interfaces:**
- Consumes: `conversation_protocol.DurableEvent`
- Produces: `EventStore.accept_action(conversation_id, command) -> tuple[bool, DurableEvent]`
- Produces: `EventStore.append(...) -> DurableEvent`
- Produces: `EventStore.replay(conversation_id, after_seq) -> list[DurableEvent]`

- [ ] **Step 1: Write failing Event Store tests**

```python
# miniapp_demo/backend/tests/test_event_store.py
import tempfile
import unittest
from pathlib import Path

from miniapp_demo.backend.conversation_protocol import ActionCommand
from miniapp_demo.backend.event_store import EventStore


class EventStoreTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = EventStore(Path(self.tempdir.name) / "events.db")

    def tearDown(self):
        self.store.close()
        self.tempdir.cleanup()

    def test_append_allocates_strict_conversation_sequence(self):
        first = self.store.append("conv-1", "runtime", "first", {})
        second = self.store.append("conv-1", "runtime", "second", {})
        other = self.store.append("conv-2", "runtime", "other", {})
        self.assertEqual([1, 2], [first.conversation_seq, second.conversation_seq])
        self.assertEqual(1, other.conversation_seq)

    def test_replay_returns_only_events_after_cursor(self):
        for number in range(3):
            self.store.append("conv-1", "runtime", f"event-{number}", {})
        self.assertEqual(
            [2, 3],
            [event.conversation_seq for event in self.store.replay("conv-1", 1)],
        )

    def test_accept_action_is_idempotent(self):
        command = ActionCommand.from_dict({
            "actionId": "act-1",
            "kind": "direct",
            "source": "ui",
            "skillId": "skill-1",
            "uiInstanceId": "ui-1",
            "name": "run",
            "args": {},
            "expectedRevision": 0,
        })
        created, first = self.store.accept_action("conv-1", command)
        duplicate, second = self.store.accept_action("conv-1", command)
        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(first.event_id, second.event_id)
        self.assertEqual(1, len(self.store.replay("conv-1", 0)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify red**

Run:

```bash
python3 -m unittest miniapp_demo.backend.tests.test_event_store -v
```

Expected: `ModuleNotFoundError: miniapp_demo.backend.event_store`.

- [ ] **Step 3: Add persistent paths to config**

```python
# miniapp_demo/backend/config.py
CONVERSATIONS_DB = MINIAPP_HOME / "conversations.db"
SKILL_STORES_DIR = MINIAPP_HOME / "skill-stores"


def ensure_directories() -> None:
    MINIAPP_HOME.mkdir(parents=True, exist_ok=True)
    APPS_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)
    SKILL_STORES_DIR.mkdir(exist_ok=True)
```

- [ ] **Step 4: Implement EventStore with `BEGIN IMMEDIATE` sequence allocation**

```python
# miniapp_demo/backend/event_store.py
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .conversation_protocol import ActionCommand, DurableEvent


class EventStore:
    def __init__(self, path: Path):
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS conversation_events (
                event_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                conversation_seq INTEGER NOT NULL,
                action_id TEXT,
                actor TEXT NOT NULL,
                type TEXT NOT NULL,
                ts TEXT NOT NULL,
                skill_id TEXT,
                ui_instance_id TEXT,
                payload_json TEXT NOT NULL,
                UNIQUE(conversation_id, conversation_seq)
            );
            CREATE INDEX IF NOT EXISTS idx_conversation_events_replay
            ON conversation_events(conversation_id, conversation_seq);
            CREATE TABLE IF NOT EXISTS conversation_actions (
                action_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                accepted_event_id TEXT NOT NULL,
                command_json TEXT NOT NULL
            );
        """)
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def append(
        self,
        conversation_id: str,
        actor: str,
        event_type: str,
        payload: Dict[str, Any],
        *,
        action_id: Optional[str] = None,
        skill_id: Optional[str] = None,
        ui_instance_id: Optional[str] = None,
    ) -> DurableEvent:
        with self._lock:
            cursor = self._connection.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            row = cursor.execute(
                "SELECT COALESCE(MAX(conversation_seq), 0) + 1 AS next_seq "
                "FROM conversation_events WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            event = DurableEvent(
                event_id=f"evt_{uuid4().hex}",
                conversation_id=conversation_id,
                conversation_seq=int(row["next_seq"]),
                actor=actor,
                type=event_type,
                ts=datetime.now(timezone.utc).isoformat(),
                payload=dict(payload),
                action_id=action_id,
                skill_id=skill_id,
                ui_instance_id=ui_instance_id,
            )
            self._insert(cursor, event)
            self._connection.commit()
            return event

    def accept_action(
        self, conversation_id: str, command: ActionCommand
    ) -> Tuple[bool, DurableEvent]:
        with self._lock:
            existing = self._connection.execute(
                "SELECT accepted_event_id FROM conversation_actions WHERE action_id = ?",
                (command.action_id,),
            ).fetchone()
            if existing:
                return False, self.get(existing["accepted_event_id"])
            event = self.append(
                conversation_id,
                "runtime",
                "action.accepted",
                {"kind": command.kind, "source": command.source},
                action_id=command.action_id,
                skill_id=command.skill_id,
                ui_instance_id=command.ui_instance_id,
            )
            self._connection.execute(
                "INSERT INTO conversation_actions VALUES (?, ?, ?, ?)",
                (
                    command.action_id,
                    conversation_id,
                    event.event_id,
                    json.dumps(command.__dict__, ensure_ascii=False),
                ),
            )
            self._connection.commit()
            return True, event

    def replay(self, conversation_id: str, after_seq: int) -> List[DurableEvent]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM conversation_events "
                "WHERE conversation_id = ? AND conversation_seq > ? "
                "ORDER BY conversation_seq",
                (conversation_id, after_seq),
            ).fetchall()
            return [self._from_row(row) for row in rows]

    def get(self, event_id: str) -> DurableEvent:
        row = self._connection.execute(
            "SELECT * FROM conversation_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if row is None:
            raise KeyError(event_id)
        return self._from_row(row)

    def _insert(self, cursor: sqlite3.Cursor, event: DurableEvent) -> None:
        cursor.execute(
            "INSERT INTO conversation_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.conversation_id,
                event.conversation_seq,
                event.action_id,
                event.actor,
                event.type,
                event.ts,
                event.skill_id,
                event.ui_instance_id,
                json.dumps(event.payload, ensure_ascii=False),
            ),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DurableEvent:
        return DurableEvent(
            event_id=row["event_id"],
            conversation_id=row["conversation_id"],
            conversation_seq=row["conversation_seq"],
            action_id=row["action_id"],
            actor=row["actor"],
            type=row["type"],
            ts=row["ts"],
            skill_id=row["skill_id"],
            ui_instance_id=row["ui_instance_id"],
            payload=json.loads(row["payload_json"]),
        )
```

- [ ] **Step 5: Run Event Store tests**

Run:

```bash
python3 -m unittest miniapp_demo.backend.tests.test_event_store -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add miniapp_demo/backend/config.py miniapp_demo/backend/event_store.py miniapp_demo/backend/tests/test_event_store.py
git commit -m "feat: persist replayable conversation events"
```

---

### Task 3: Extend NDJSON Metadata to `ui_command`

**Files:**
- Modify: `miniapp_demo/backend/script_metadata.py:105-175`
- Modify: `miniapp_demo/backend/tests/test_script_metadata.py`

**Interfaces:**
- Consumes: `UiCommand.from_dict`
- Produces: `parse_result_file(...)[“uiCommands”]`
- Preserves: existing size, UTF-8, finite number, owner-only file protections

- [ ] **Step 1: Add failing metadata tests**

Append to `miniapp_demo/backend/tests/test_script_metadata.py`:

```python
def test_accepts_ui_command_and_aggregates_in_order(self):
    events = [
        {
            "type": "ui_command",
            "command": "open",
            "route": "/orders/1042",
            "payload": {"orderId": "1042"},
            "expectedRevision": 7,
        },
        {
            "type": "ui_command",
            "command": "show_content",
            "route": "/orders/1042",
            "payload": {"status": "approved"},
            "expectedRevision": 8,
        },
    ]
    result = script_metadata.aggregate_events(events)
    self.assertEqual(events, result["uiCommands"])

def test_rejects_unknown_ui_command(self):
    with self.assertRaises(script_metadata.MetadataValidationError):
        script_metadata.validate_event({
            "type": "ui_command",
            "command": "execute_javascript",
            "payload": {},
            "expectedRevision": 0,
        })
```

- [ ] **Step 2: Run focused tests and verify red**

Run:

```bash
python3 -m unittest miniapp_demo.backend.tests.test_script_metadata -v
```

Expected: `unsupported metadata event type: 'ui_command'`.

- [ ] **Step 3: Validate and aggregate `ui_command`**

In `validate_event`:

```python
    elif event_type == "ui_command":
        from .conversation_protocol import UiCommand

        try:
            UiCommand.from_dict(event)
        except ValueError as exc:
            raise MetadataValidationError(str(exc)) from exc
```

Replace `aggregate_events` with:

```python
def aggregate_events(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ui_updates: list[dict[str, Any]] = []
    ui_commands: list[dict[str, Any]] = []
    agent_signal = None
    for raw_event in events:
        event = validate_event(dict(raw_event))
        if event["type"] == "ui_update":
            ui_updates.append(event["structuredContent"])
        elif event["type"] == "ui_command":
            ui_commands.append(dict(event))
        else:
            agent_signal = "end_turn"
    return {
        "uiUpdates": ui_updates,
        "uiCommands": ui_commands,
        "agentSignal": agent_signal,
    }
```

Do not remove legacy `ui_update` support in this task; existing bundled apps still depend on it until the Host integration plan.

- [ ] **Step 4: Run metadata and sandbox regression tests**

Run:

```bash
python3 -m unittest \
  miniapp_demo.backend.tests.test_script_metadata \
  miniapp_demo.backend.tests.test_sandbox \
  miniapp_demo.backend.tests.test_agent_bash_metadata -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add miniapp_demo/backend/script_metadata.py miniapp_demo/backend/tests/test_script_metadata.py
git commit -m "feat: accept structured UI commands from skill scripts"
```

---

### Task 4: Implement Persistent Store and Generic Direct Relay

**Files:**
- Create: `miniapp_demo/backend/persistent_store.py`
- Create: `miniapp_demo/backend/direct_relay.py`
- Create: `miniapp_demo/backend/tests/test_persistent_store.py`
- Create: `miniapp_demo/backend/tests/test_direct_relay.py`

**Interfaces:**
- Consumes: `config.SKILL_STORES_DIR`
- Consumes: `app_registry.get_app`, `sandbox.run_script`
- Produces: `PersistentStore.path_for(user, skill_id) -> Path`
- Produces: `DirectRelay.execute(command, user) -> list[dict[str, Any]]`

- [ ] **Step 1: Write failing persistent store tests**

```python
# miniapp_demo/backend/tests/test_persistent_store.py
import tempfile
import unittest
from pathlib import Path

from miniapp_demo.backend.persistent_store import PersistentStore


class PersistentStoreTest(unittest.TestCase):
    def test_is_stable_per_user_and_skill_but_not_conversation(self):
        with tempfile.TemporaryDirectory() as root:
            store = PersistentStore(Path(root))
            first = store.path_for("alice", "order-review")
            second = store.path_for("alice", "order-review")
            other_user = store.path_for("bob", "order-review")
            self.assertEqual(first, second)
            self.assertNotEqual(first, other_user)
            self.assertTrue(first.is_dir())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            store = PersistentStore(Path(root))
            with self.assertRaises(ValueError):
                store.path_for("../alice", "skill")
```

- [ ] **Step 2: Write failing Direct Relay tests**

```python
# miniapp_demo/backend/tests/test_direct_relay.py
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from miniapp_demo.backend.conversation_protocol import ActionCommand
from miniapp_demo.backend.direct_relay import DirectActionError, DirectRelay


class FakePersistentStore:
    def path_for(self, user, skill_id):
        return Path("/tmp") / user / skill_id


class DirectRelayTest(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_manifest_and_returns_ui_commands(self):
        script = SimpleNamespace(path="scripts/approve.py", visibility=["ui"])
        manifest = SimpleNamespace(
            root=Path("/apps/order-review"),
            script_by_name=lambda name: script if name == "approve" else None,
        )
        run_script = AsyncMock(return_value=SimpleNamespace(
            ok=True,
            error=None,
            miniapp_metadata={
                "uiCommands": [{
                    "type": "ui_command",
                    "command": "show_content",
                    "route": "/orders/1042",
                    "payload": {"status": "approved"},
                    "expectedRevision": 7,
                }]
            },
        ))
        relay = DirectRelay(
            get_skill=lambda skill_id: manifest,
            run_script=run_script,
            persistent_store=FakePersistentStore(),
        )
        command = ActionCommand.from_dict({
            "actionId": "act-1",
            "kind": "direct",
            "source": "ui",
            "skillId": "order-review",
            "uiInstanceId": "ui-1",
            "name": "approve",
            "args": {"orderId": "1042"},
            "expectedRevision": 7,
        })
        result = await relay.execute(command, user="alice")
        self.assertEqual("show_content", result[0]["command"])
        run_script.assert_awaited_once()

    async def test_rejects_action_without_ui_visibility(self):
        script = SimpleNamespace(path="scripts/private.py", visibility=["agent"])
        manifest = SimpleNamespace(
            root=Path("/apps/skill"),
            script_by_name=lambda name: script,
        )
        relay = DirectRelay(
            get_skill=lambda skill_id: manifest,
            run_script=AsyncMock(),
            persistent_store=FakePersistentStore(),
        )
        command = ActionCommand.from_dict({
            "actionId": "act-1",
            "kind": "direct",
            "source": "ui",
            "skillId": "skill",
            "uiInstanceId": "ui-1",
            "name": "private",
            "args": {},
            "expectedRevision": 0,
        })
        with self.assertRaises(DirectActionError):
            await relay.execute(command, user="alice")
```

- [ ] **Step 3: Run tests and verify red**

Run:

```bash
python3 -m unittest \
  miniapp_demo.backend.tests.test_persistent_store \
  miniapp_demo.backend.tests.test_direct_relay -v
```

Expected: both modules are missing.

- [ ] **Step 4: Implement PersistentStore**

```python
# miniapp_demo/backend/persistent_store.py
from pathlib import Path
import re


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class PersistentStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path_for(self, user: str, skill_id: str) -> Path:
        if not _SAFE_ID.fullmatch(user) or not _SAFE_ID.fullmatch(skill_id):
            raise ValueError("user and skill_id must be safe identifiers")
        path = self.root / user / skill_id
        path.mkdir(parents=True, exist_ok=True)
        return path
```

- [ ] **Step 5: Implement DirectRelay**

```python
# miniapp_demo/backend/direct_relay.py
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List

from . import app_registry, config, sandbox
from .conversation_protocol import ActionCommand
from .persistent_store import PersistentStore


class DirectActionError(RuntimeError):
    pass


class DirectRelay:
    def __init__(
        self,
        *,
        get_skill: Callable[[str], Any] = app_registry.get_app,
        run_script: Callable[..., Awaitable[Any]] = sandbox.run_script,
        persistent_store: PersistentStore | None = None,
    ):
        self._get_skill = get_skill
        self._run_script = run_script
        self._persistent_store = persistent_store or PersistentStore(
            config.SKILL_STORES_DIR
        )

    async def execute(
        self, command: ActionCommand, *, user: str
    ) -> List[Dict[str, Any]]:
        if command.kind != "direct" or not command.skill_id or not command.name:
            raise DirectActionError("direct command is required")
        manifest = self._get_skill(command.skill_id)
        if manifest is None:
            raise DirectActionError("skill not found")
        script = manifest.script_by_name(command.name)
        if script is None or "ui" not in script.visibility:
            raise DirectActionError(f"unknown direct action: {command.name}")
        store_dir = self._persistent_store.path_for(user, command.skill_id)
        result = await self._run_script(
            manifest.root / script.path,
            manifest.root,
            store_dir,
            command.args,
        )
        if not result.ok:
            raise DirectActionError(result.error or "direct action failed")
        metadata = result.miniapp_metadata or {}
        return [dict(item) for item in metadata.get("uiCommands", [])]
```

- [ ] **Step 6: Run focused and sandbox regression tests**

Run:

```bash
python3 -m unittest \
  miniapp_demo.backend.tests.test_persistent_store \
  miniapp_demo.backend.tests.test_direct_relay \
  miniapp_demo.backend.tests.test_sandbox -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add \
  miniapp_demo/backend/persistent_store.py \
  miniapp_demo/backend/direct_relay.py \
  miniapp_demo/backend/tests/test_persistent_store.py \
  miniapp_demo/backend/tests/test_direct_relay.py
git commit -m "feat: route direct actions through generic skill relay"
```

---

### Task 5: Add Event Hub and Conversation Runtime

**Files:**
- Create: `miniapp_demo/backend/event_hub.py`
- Create: `miniapp_demo/backend/conversation_runtime.py`
- Create: `miniapp_demo/backend/tests/test_event_hub.py`
- Create: `miniapp_demo/backend/tests/test_conversation_runtime.py`

**Interfaces:**
- Consumes: `EventStore`, `DirectRelay`
- Produces: `EventHub.version(conversation_id) -> int`
- Produces: `EventHub.wait_for_change(conversation_id, seen_version)`
- Produces: `ConversationRuntime.submit(conversation_id, raw, user) -> ActionAck`
- Produces: `ConversationRuntime.subscribe(conversation_id, after_seq)`
- Produces: `ConversationRuntime.wait_idle()`

- [ ] **Step 1: Write failing EventHub race test**

```python
# miniapp_demo/backend/tests/test_event_hub.py
import asyncio
import unittest

from miniapp_demo.backend.event_hub import EventHub


class EventHubTest(unittest.IsolatedAsyncioTestCase):
    async def test_waiter_observes_change_after_seen_version(self):
        hub = EventHub()
        seen = hub.version("conv-1")
        waiter = asyncio.create_task(hub.wait_for_change("conv-1", seen))
        await asyncio.sleep(0)
        await hub.publish("conv-1")
        self.assertEqual(1, await asyncio.wait_for(waiter, 0.1))
```

- [ ] **Step 2: Write failing Runtime direct-flow tests**

```python
# miniapp_demo/backend/tests/test_conversation_runtime.py
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from miniapp_demo.backend.conversation_runtime import ConversationRuntime
from miniapp_demo.backend.event_store import EventStore


class ConversationRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = EventStore(Path(self.tempdir.name) / "events.db")
        self.relay = AsyncMock()
        self.relay.execute.return_value = [{
            "type": "ui_command",
            "command": "show_content",
            "route": "/result",
            "payload": {"status": "approved"},
            "expectedRevision": 0,
        }]
        self.runtime = ConversationRuntime(self.store, self.relay)

    async def asyncTearDown(self):
        await self.runtime.shutdown()
        self.store.close()
        self.tempdir.cleanup()

    async def test_direct_action_emits_lifecycle_and_ui_command(self):
        ack = await self.runtime.submit("conv-1", {
            "actionId": "act-1",
            "kind": "direct",
            "source": "ui",
            "skillId": "order-review",
            "uiInstanceId": "ui-1",
            "name": "approve",
            "args": {"orderId": "1042"},
            "expectedRevision": 0,
        }, user="alice")
        await self.runtime.wait_idle()
        events = self.store.replay("conv-1", 0)
        self.assertEqual("accepted", ack["status"])
        self.assertEqual([
            "action.accepted",
            "direct_action.started",
            "ui.command",
            "direct_action.completed",
        ], [event.type for event in events])

    async def test_duplicate_action_does_not_execute_twice(self):
        raw = {
            "actionId": "act-1",
            "kind": "direct",
            "source": "ui",
            "skillId": "order-review",
            "uiInstanceId": "ui-1",
            "name": "approve",
            "args": {},
            "expectedRevision": 0,
        }
        await self.runtime.submit("conv-1", raw, user="alice")
        await self.runtime.submit("conv-1", raw, user="alice")
        await self.runtime.wait_idle()
        self.relay.execute.assert_awaited_once()
```

- [ ] **Step 3: Run tests and verify red**

Run:

```bash
python3 -m unittest \
  miniapp_demo.backend.tests.test_event_hub \
  miniapp_demo.backend.tests.test_conversation_runtime -v
```

Expected: missing modules.

- [ ] **Step 4: Implement EventHub**

```python
# miniapp_demo/backend/event_hub.py
import asyncio
from collections import defaultdict


class EventHub:
    def __init__(self):
        self._conditions = defaultdict(asyncio.Condition)
        self._versions = defaultdict(int)

    def version(self, conversation_id: str) -> int:
        return self._versions[conversation_id]

    async def publish(self, conversation_id: str) -> int:
        condition = self._conditions[conversation_id]
        async with condition:
            self._versions[conversation_id] += 1
            condition.notify_all()
            return self._versions[conversation_id]

    async def wait_for_change(self, conversation_id: str, seen: int) -> int:
        condition = self._conditions[conversation_id]
        async with condition:
            await condition.wait_for(
                lambda: self._versions[conversation_id] != seen
            )
            return self._versions[conversation_id]
```

- [ ] **Step 5: Implement ConversationRuntime**

```python
# miniapp_demo/backend/conversation_runtime.py
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, Set

from .conversation_protocol import ActionCommand, DurableEvent
from .direct_relay import DirectRelay
from .event_hub import EventHub
from .event_store import EventStore


class ConversationRuntime:
    def __init__(
        self,
        store: EventStore,
        direct_relay: DirectRelay,
        hub: EventHub | None = None,
    ):
        self.store = store
        self.direct_relay = direct_relay
        self.hub = hub or EventHub()
        self._tasks: Set[asyncio.Task] = set()

    async def submit(
        self, conversation_id: str, raw: Dict[str, Any], *, user: str
    ) -> Dict[str, str]:
        command = ActionCommand.from_dict(raw)
        created, accepted = self.store.accept_action(conversation_id, command)
        if not created:
            return {
                "actionId": command.action_id,
                "status": "duplicate",
                "acceptedEventId": accepted.event_id,
            }
        await self.hub.publish(conversation_id)
        if command.kind != "direct":
            raise ValueError("agent actions are not enabled in foundation phase")
        task = asyncio.create_task(
            self._run_direct(conversation_id, command, user=user)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return {
            "actionId": command.action_id,
            "status": "accepted",
            "acceptedEventId": accepted.event_id,
        }

    async def _append(self, conversation_id: str, *args, **kwargs) -> DurableEvent:
        event = self.store.append(conversation_id, *args, **kwargs)
        await self.hub.publish(conversation_id)
        return event

    async def _run_direct(
        self, conversation_id: str, command: ActionCommand, *, user: str
    ) -> None:
        common = {
            "action_id": command.action_id,
            "skill_id": command.skill_id,
            "ui_instance_id": command.ui_instance_id,
        }
        await self._append(
            conversation_id, "runtime", "direct_action.started", {}, **common
        )
        try:
            commands = await self.direct_relay.execute(command, user=user)
            for ui_command in commands:
                await self._append(
                    conversation_id,
                    "tool",
                    "ui.command",
                    ui_command,
                    **common,
                )
        except Exception as exc:
            await self._append(
                conversation_id,
                "runtime",
                "direct_action.failed",
                {"error": str(exc)},
                **common,
            )
        else:
            await self._append(
                conversation_id,
                "runtime",
                "direct_action.completed",
                {},
                **common,
            )

    async def subscribe(
        self, conversation_id: str, after_seq: int
    ) -> AsyncIterator[DurableEvent]:
        cursor = after_seq
        while True:
            seen = self.hub.version(conversation_id)
            events = self.store.replay(conversation_id, cursor)
            if events:
                for event in events:
                    cursor = event.conversation_seq
                    yield event
                continue
            await self.hub.wait_for_change(conversation_id, seen)

    async def wait_idle(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
```

- [ ] **Step 6: Run Runtime tests**

Run:

```bash
python3 -m unittest \
  miniapp_demo.backend.tests.test_event_hub \
  miniapp_demo.backend.tests.test_conversation_runtime -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add \
  miniapp_demo/backend/event_hub.py \
  miniapp_demo/backend/conversation_runtime.py \
  miniapp_demo/backend/tests/test_event_hub.py \
  miniapp_demo/backend/tests/test_conversation_runtime.py
git commit -m "feat: run direct actions on conversation event stream"
```

---

### Task 6: Expose Command POST and Conversation SSE

**Files:**
- Create: `miniapp_demo/backend/routers/conversation_router.py`
- Create: `miniapp_demo/backend/tests/test_conversation_router.py`
- Modify: `miniapp_demo/backend/main.py:11-18,29-46`

**Interfaces:**
- Consumes: `ConversationRuntime.submit`, `subscribe`, `shutdown`
- Produces: `POST /api/conversations/{conversation_id}/actions`
- Produces: `GET /api/conversations/{conversation_id}/events?after=N`

- [ ] **Step 1: Write failing router contract tests**

```python
# miniapp_demo/backend/tests/test_conversation_router.py
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from miniapp_demo.backend.conversation_protocol import DurableEvent
from miniapp_demo.backend.routers import conversation_router


class FakeConversationRuntime:
    def __init__(self):
        self.submitted = []

    async def submit(self, conversation_id, raw, *, user):
        self.submitted.append((conversation_id, raw, user))
        return {
            "actionId": raw["actionId"],
            "status": "accepted",
            "acceptedEventId": "evt-1",
        }

    async def subscribe(self, conversation_id, after_seq):
        yield DurableEvent(
            event_id="evt-1",
            conversation_id=conversation_id,
            conversation_seq=after_seq + 1,
            actor="runtime",
            type="action.accepted",
            ts="2026-07-15T00:00:00+00:00",
            payload={"kind": "direct"},
            action_id="act-1",
        )


class ConversationRouterTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(conversation_router.router)
        self.client = TestClient(app)
        self.runtime = FakeConversationRuntime()
        self.patcher = patch.object(
            conversation_router, "conversation_runtime", self.runtime
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_post_action_returns_ack(self):
        response = self.client.post(
            "/api/conversations/conv-1/actions",
            headers={"X-Miniapp-User": "alice"},
            json={
                "actionId": "act-1",
                "kind": "direct",
                "source": "ui",
                "skillId": "order-review",
                "uiInstanceId": "ui-1",
                "name": "approve",
                "args": {},
                "expectedRevision": 0,
            },
        )
        self.assertEqual(202, response.status_code)
        self.assertEqual("accepted", response.json()["status"])
        self.assertEqual("alice", self.runtime.submitted[0][2])

    def test_sse_replays_after_cursor(self):
        response = self.client.get(
            "/api/conversations/conv-1/events?after=4"
        )
        expected = self.runtime.submitted
        self.assertEqual(200, response.status_code)
        frame = json.loads(response.text.split("data: ", 1)[1])
        self.assertEqual(5, frame["conversationSeq"])
```

- [ ] **Step 2: Run router test and verify red**

Run:

```bash
python3 -m unittest miniapp_demo.backend.tests.test_conversation_router -v
```

Expected: import failure for `conversation_router`.

- [ ] **Step 3: Implement Router and global Runtime**

```python
# miniapp_demo/backend/routers/conversation_router.py
from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Body, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import config
from ..conversation_protocol import ProtocolValidationError
from ..conversation_runtime import ConversationRuntime
from ..direct_relay import DirectRelay
from ..event_store import EventStore


router = APIRouter(prefix="/api/conversations", tags=["conversations"])
conversation_event_store = EventStore(config.CONVERSATIONS_DB)
conversation_runtime = ConversationRuntime(
    conversation_event_store,
    DirectRelay(),
)


@router.post("/{conversation_id}/actions", status_code=202)
async def submit_action(
    conversation_id: str,
    raw: Dict[str, Any] = Body(...),
    user: str = Header("local", alias="X-Miniapp-User"),
):
    try:
        return await conversation_runtime.submit(conversation_id, raw, user=user)
    except ProtocolValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{conversation_id}/events")
async def subscribe_events(
    conversation_id: str,
    after: int = Query(0, ge=0),
):
    async def encode_sse():
        async for event in conversation_runtime.subscribe(conversation_id, after):
            payload = json.dumps(event.to_dict(), ensure_ascii=False)
            yield f"id: {event.conversation_seq}\ndata: {payload}\n\n"

    return StreamingResponse(
        encode_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 4: Register router and shutdown**

In `main.py`, import and include `conversation_router`:

```python
from .routers import (
    apps_router,
    asr_router,
    chat_router,
    config_router,
    conversation_router,
    files_router,
    runtime_router,
)

app.include_router(conversation_router.router)
```

Extend `_shutdown`:

```python
@app.on_event("shutdown")
async def _shutdown() -> None:
    await runtime_router.runtime_service.shutdown()
    await conversation_router.conversation_runtime.shutdown()
    conversation_router.conversation_event_store.close()
```

- [ ] **Step 5: Run router and existing runtime router tests**

Run:

```bash
python3 -m unittest \
  miniapp_demo.backend.tests.test_conversation_router \
  miniapp_demo.backend.tests.test_runtime_router -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add \
  miniapp_demo/backend/routers/conversation_router.py \
  miniapp_demo/backend/tests/test_conversation_router.py \
  miniapp_demo/backend/main.py
git commit -m "feat: expose conversation command and SSE APIs"
```

---

### Task 7: Add Frontend Conversation Types and Command Client

**Files:**
- Create: `miniapp_demo/frontend/src/types/conversation.ts`
- Create: `miniapp_demo/frontend/src/types/conversation.test.ts`
- Create: `miniapp_demo/frontend/src/transport/postAction.ts`
- Create: `miniapp_demo/frontend/src/transport/postAction.test.ts`

**Interfaces:**
- Produces: `ActionCommand`, `DurableEvent`, `UiCommand`, `ActionAck`
- Produces: `postAction(conversationId, command, signal?)`

- [ ] **Step 1: Write failing type guard and transport tests**

```typescript
// miniapp_demo/frontend/src/types/conversation.test.ts
import { describe, expect, it } from "vitest";
import { parseDurableEvent } from "./conversation";

describe("parseDurableEvent", () => {
  it("accepts a durable event and rejects invalid sequence", () => {
    expect(parseDurableEvent({
      eventId: "evt-1",
      conversationId: "conv-1",
      conversationSeq: 1,
      actor: "runtime",
      type: "action.accepted",
      ts: "2026-07-15T00:00:00Z",
      payload: {},
    }).conversationSeq).toBe(1);

    expect(() => parseDurableEvent({
      eventId: "evt-1",
      conversationId: "conv-1",
      conversationSeq: -1,
      actor: "runtime",
      type: "action.accepted",
      ts: "2026-07-15T00:00:00Z",
      payload: {},
    })).toThrow("conversationSeq");
  });
});
```

```typescript
// miniapp_demo/frontend/src/transport/postAction.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { postAction } from "./postAction";

afterEach(() => vi.unstubAllGlobals());

describe("postAction", () => {
  it("POSTs a command and parses the ACK", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      actionId: "act-1",
      status: "accepted",
      acceptedEventId: "evt-1",
    }), {
      status: 202,
      headers: { "content-type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const command = {
      actionId: "act-1",
      kind: "direct" as const,
      source: "ui" as const,
      skillId: "order-review",
      uiInstanceId: "ui-1",
      name: "approve",
      args: {},
      expectedRevision: 0,
    };
    await expect(postAction("conv-1", command)).resolves.toEqual({
      actionId: "act-1",
      status: "accepted",
      acceptedEventId: "evt-1",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/conversations/conv-1/actions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(command),
      }),
    );
  });
});
```

- [ ] **Step 2: Run tests and verify red**

Run:

```bash
cd miniapp_demo/frontend
npm test -- --run src/types/conversation.test.ts src/transport/postAction.test.ts
```

Expected: missing modules.

- [ ] **Step 3: Implement types and validation**

```typescript
// miniapp_demo/frontend/src/types/conversation.ts
import type { JsonValue } from "./index";

export type ActionKind = "agent" | "direct";
export type ActionSource = "chat" | "ui";

export interface ActionCommand {
  actionId: string;
  kind: ActionKind;
  source: ActionSource;
  skillId?: string;
  uiInstanceId?: string;
  intent?: string;
  name?: string;
  args?: Record<string, JsonValue>;
  expectedRevision?: number;
}

export interface ActionAck {
  actionId: string;
  status: "accepted" | "duplicate";
  acceptedEventId: string;
}

export interface DurableEvent {
  eventId: string;
  conversationId: string;
  conversationSeq: number;
  actor: "user" | "agent" | "tool" | "runtime";
  type: string;
  ts: string;
  payload: Record<string, JsonValue>;
  actionId?: string;
  skillId?: string;
  uiInstanceId?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseDurableEvent(value: unknown): DurableEvent {
  if (!isRecord(value)) throw new Error("event must be an object");
  if (typeof value.eventId !== "string" || !value.eventId) {
    throw new Error("eventId is required");
  }
  if (typeof value.conversationId !== "string" || !value.conversationId) {
    throw new Error("conversationId is required");
  }
  if (!Number.isInteger(value.conversationSeq) || Number(value.conversationSeq) < 1) {
    throw new Error("conversationSeq must be a positive integer");
  }
  if (!["user", "agent", "tool", "runtime"].includes(String(value.actor))) {
    throw new Error("actor is invalid");
  }
  if (typeof value.type !== "string" || !value.type) {
    throw new Error("type is required");
  }
  if (typeof value.ts !== "string" || !isRecord(value.payload)) {
    throw new Error("ts and payload are required");
  }
  return value as unknown as DurableEvent;
}
```

- [ ] **Step 4: Implement `postAction`**

```typescript
// miniapp_demo/frontend/src/transport/postAction.ts
import type { ActionAck, ActionCommand } from "../types/conversation";

export async function postAction(
  conversationId: string,
  command: ActionCommand,
  signal?: AbortSignal,
): Promise<ActionAck> {
  const response = await fetch(
    `/api/conversations/${encodeURIComponent(conversationId)}/actions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(command),
      signal,
    },
  );
  if (!response.ok) {
    throw new Error(`Action submission failed: HTTP ${response.status}`);
  }
  return response.json() as Promise<ActionAck>;
}
```

- [ ] **Step 5: Run tests and typecheck**

Run:

```bash
cd miniapp_demo/frontend
npm test -- --run src/types/conversation.test.ts src/transport/postAction.test.ts
npm run typecheck
```

Expected: tests and typecheck pass.

- [ ] **Step 6: Commit**

```bash
git add \
  miniapp_demo/frontend/src/types/conversation.ts \
  miniapp_demo/frontend/src/types/conversation.test.ts \
  miniapp_demo/frontend/src/transport/postAction.ts \
  miniapp_demo/frontend/src/transport/postAction.test.ts
git commit -m "feat: add conversation action client"
```

---

### Task 8: Add Frontend Conversation SSE Client

**Files:**
- Create: `miniapp_demo/frontend/src/transport/conversationStream.ts`
- Create: `miniapp_demo/frontend/src/transport/conversationStream.test.ts`

**Interfaces:**
- Consumes: `parseDurableEvent`
- Produces: `subscribeConversationEvents(conversationId, afterSeq, onEvent, signal)`
- Guarantees: duplicate/older `conversationSeq` dropped; gap is an error; caller owns reconnect

- [ ] **Step 1: Write failing stream parser tests**

```typescript
// miniapp_demo/frontend/src/transport/conversationStream.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { subscribeConversationEvents } from "./conversationStream";

const encoder = new TextEncoder();

function responseFrom(text: string): Response {
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      for (const byte of encoder.encode(text)) {
        controller.enqueue(Uint8Array.of(byte));
      }
      controller.close();
    },
  }), {
    headers: { "content-type": "text/event-stream; charset=utf-8" },
  });
}

function event(seq: number) {
  return {
    eventId: `evt-${seq}`,
    conversationId: "conv-1",
    conversationSeq: seq,
    actor: "runtime",
    type: "test.event",
    ts: "2026-07-15T00:00:00Z",
    payload: {},
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("subscribeConversationEvents", () => {
  it("parses arbitrary chunks and drops duplicate sequence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseFrom(
      `id: 1\ndata: ${JSON.stringify(event(1))}\n\n` +
      `id: 1\ndata: ${JSON.stringify(event(1))}\n\n` +
      `id: 2\ndata: ${JSON.stringify(event(2))}\n\n`,
    )));
    const received: number[] = [];
    await subscribeConversationEvents(
      "conv-1",
      0,
      (item) => received.push(item.conversationSeq),
    );
    expect(received).toEqual([1, 2]);
  });

  it("rejects a sequence gap", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseFrom(
      `data: ${JSON.stringify(event(1))}\n\n` +
      `data: ${JSON.stringify(event(3))}\n\n`,
    )));
    await expect(subscribeConversationEvents(
      "conv-1", 0, vi.fn(),
    )).rejects.toThrow("sequence gap");
  });
});
```

- [ ] **Step 2: Run test and verify red**

Run:

```bash
cd miniapp_demo/frontend
npm test -- --run src/transport/conversationStream.test.ts
```

Expected: missing module.

- [ ] **Step 3: Implement the Conversation SSE client**

Extract the line parser from `streamAction.ts` into the new module, preserving support for CRLF, comments, multiline `data`, and UTF-8 chunk boundaries. The dispatch rule must be:

```typescript
const event = parseDurableEvent(JSON.parse(dataLines.join("\n")));
if (event.conversationId !== conversationId) {
  throw new Error("conversationId mismatch");
}
if (event.conversationSeq <= highestSeq) return;
if (event.conversationSeq !== highestSeq + 1) {
  throw new Error(
    `conversation sequence gap: expected ${highestSeq + 1}, received ${event.conversationSeq}`,
  );
}
highestSeq = event.conversationSeq;
await onEvent(event);
```

The fetch setup must be:

```typescript
const response = await fetch(
  `/api/conversations/${encodeURIComponent(conversationId)}/events?after=${afterSeq}`,
  {
    headers: { Accept: "text/event-stream" },
    signal,
  },
);
```

Unlike `streamAction`, EOF is allowed because the caller reconnects using the last delivered sequence. Do not call a cancel endpoint when this stream closes.

- [ ] **Step 4: Run stream tests and typecheck**

Run:

```bash
cd miniapp_demo/frontend
npm test -- --run \
  src/transport/conversationStream.test.ts \
  src/transport/streamAction.test.ts
npm run typecheck
```

Expected: both old and new stream suites pass; typecheck passes.

- [ ] **Step 5: Commit**

```bash
git add \
  miniapp_demo/frontend/src/transport/conversationStream.ts \
  miniapp_demo/frontend/src/transport/conversationStream.test.ts
git commit -m "feat: subscribe to replayable conversation SSE"
```

---

### Task 9: Verify the Foundation Vertical Slice

**Files:**
- Modify only if verification exposes defects in files from Tasks 1–8.

**Interfaces:**
- Verifies the full contract across backend and frontend.

- [ ] **Step 1: Run focused backend tests**

```bash
python3 -m unittest \
  miniapp_demo.backend.tests.test_conversation_protocol \
  miniapp_demo.backend.tests.test_event_store \
  miniapp_demo.backend.tests.test_event_hub \
  miniapp_demo.backend.tests.test_persistent_store \
  miniapp_demo.backend.tests.test_direct_relay \
  miniapp_demo.backend.tests.test_conversation_runtime \
  miniapp_demo.backend.tests.test_conversation_router \
  miniapp_demo.backend.tests.test_script_metadata -v
```

Expected: all focused backend tests pass.

- [ ] **Step 2: Run full backend regression suite**

```bash
python3 -m unittest discover \
  -s miniapp_demo/backend/tests \
  -p 'test_*.py' -v
```

Expected: all backend tests pass. Existing v0.3 tests remain green during the transitional implementation stage.

- [ ] **Step 3: Run frontend tests**

```bash
cd miniapp_demo/frontend
npm test -- --run
```

Expected: all Vitest suites pass.

- [ ] **Step 4: Run frontend static verification**

```bash
cd miniapp_demo/frontend
npm run typecheck
npm run build
```

Expected: typecheck and Vite build exit 0.

- [ ] **Step 5: Manually smoke the new API**

Start the existing demo, subscribe in one terminal, and submit a bundled Skill Direct Action in another:

```bash
bash miniapp_demo/run.sh
```

```bash
curl -N \
  "http://localhost:8790/api/conversations/smoke-conv/events?after=0"
```

```bash
curl -i \
  -H "Content-Type: application/json" \
  -H "X-Miniapp-User: local" \
  -d '{
    "actionId":"smoke-direct-1",
    "kind":"direct",
    "source":"ui",
    "skillId":"order-review",
    "uiInstanceId":"smoke-ui-1",
    "name":"list_orders",
    "args":{},
    "expectedRevision":0
  }' \
  "http://localhost:8790/api/conversations/smoke-conv/actions"
```

Expected:

- POST returns HTTP 202 with `status=accepted`.
- SSE emits consecutive `conversationSeq` values.
- Event order is `action.accepted`, `direct_action.started`, zero or more `ui.command`, then `direct_action.completed`.
- Reconnecting with `after=<lastSeq-1>` replays exactly the final event.

- [ ] **Step 6: Commit any verification-only fixes**

If verification required no fixes, skip this commit. Otherwise:

```bash
git add <only-files-fixed-during-verification>
git commit -m "fix: stabilize conversation runtime foundation"
```

---

## Completion Criteria

The foundation plan is complete only when:

1. Direct Action Command POST is idempotent by `actionId`.
2. Durable Events survive process restart in SQLite.
3. Multiple SSE consumers can replay the same ordered stream.
4. Direct Relay contains no Skill-specific business branches.
5. Direct Action uses `user × skill` persistence and does not write Agent history.
6. `ui_command` uses the existing secure NDJSON result path.
7. Frontend can submit Commands and consume ordered Conversation SSE.
8. Existing backend/frontend suites, typecheck, and build all pass.

After this foundation lands, create and execute:

- `2026-07-15-unified-agent-context.md`
- `2026-07-15-host-ui-integration.md`
