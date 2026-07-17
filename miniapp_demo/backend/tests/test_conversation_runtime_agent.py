import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from miniapp_demo.backend.conversations.event_store import EventStore
from miniapp_demo.backend.conversations.runtime import ConversationRuntime


class ConversationRuntimeAgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EventStore(Path(self.tmp.name))
        self.runtime = ConversationRuntime(self.store)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    @patch("miniapp_demo.backend.conversations.runtime.run_unified_agent_turn")
    async def test_agent_action_without_ui_skips_snapshot(self, run_turn):
        class FakeEvent:
            event_type = "task_complete"
            content = []
            metadata = None

            def to_dict(self):
                return {}

        run_turn.return_value = iter([FakeEvent()])

        result = await self.runtime.submit_action({
            "conversationId": "conv_1",
            "actionId": "act_1",
            "kind": "agent",
            "source": "chat",
            "intent": "查询订单 1042",
        })
        self.assertEqual(result["status"], "enqueued")
        await asyncio.sleep(0.3)
        events = self.store.replay("conv_1")
        types = [e["type"] for e in events]
        self.assertIn("agent_action.started", types)
        self.assertIn("agent_action.completed", types)
        self.assertNotIn("ui.snapshot.requested", types)

    @patch("miniapp_demo.backend.conversations.runtime.project_business_context")
    @patch("miniapp_demo.backend.conversations.runtime.run_unified_agent_turn")
    async def test_agent_action_with_ui_waits_for_snapshot(self, run_turn, project):
        run_turn.side_effect = lambda **kwargs: iter(())
        project.return_value = {
            "skillId": "demo",
            "uiInstanceId": "ui_1",
            "route": "/",
            "revision": 1,
            "view": {},
            "business": {},
        }

        await self.runtime.submit_action({
            "conversationId": "conv_2",
            "actionId": "act_2",
            "kind": "agent",
            "source": "ui",
            "intent": "批准",
            "skillId": "demo",
            "uiInstanceId": "ui_1",
        })

        async def post_snapshot():
            await asyncio.sleep(0.05)
            await self.runtime.submit_snapshot("conv_2", "act_2", {
                "snapshotRequestId": "snap_act_2",
                "skillId": "demo",
                "uiInstanceId": "ui_1",
                "route": "/",
                "revision": 1,
                "env": {},
            })

        asyncio.create_task(post_snapshot())
        await asyncio.sleep(0.5)
        types = [e["type"] for e in self.store.replay("conv_2")]
        self.assertIn("ui.snapshot.received", types)
        self.assertIn("ui.loading.changed", types)


if __name__ == "__main__":
    unittest.main()
