import asyncio
import unittest

from miniapp_demo.backend.conversations.agent_lane import (
    ActionRecord,
    ActionRegistry,
    AgentLane,
)


class AgentLaneTests(unittest.IsolatedAsyncioTestCase):
    async def test_fifo_dequeue(self):
        lane = AgentLane()
        a1 = ActionRecord("a1", "conv", "agent", "chat", intent="one")
        a2 = ActionRecord("a2", "conv", "agent", "ui", intent="two")
        await lane.enqueue(a1)
        await lane.enqueue(a2)
        self.assertEqual((await lane.dequeue()).action_id, "a1")
        self.assertEqual((await lane.dequeue()).action_id, "a2")
        self.assertIsNone(await lane.dequeue())

    async def test_wait_next_unblocks_on_enqueue(self):
        lane = AgentLane()
        waiter = asyncio.create_task(lane.wait_next())
        await asyncio.sleep(0.01)
        action = ActionRecord("a1", "conv", "agent", "chat", intent="hello")
        await lane.enqueue(action)
        result = await asyncio.wait_for(waiter, timeout=1)
        self.assertEqual(result.action_id, "a1")

    async def test_cancel_queued_action(self):
        lane = AgentLane()
        await lane.enqueue(ActionRecord("a1", "conv", "agent", "chat"))
        cancelled = await lane.cancel("a1")
        self.assertTrue(cancelled)
        self.assertIsNone(await lane.dequeue())


class ActionRegistryTests(unittest.TestCase):
    def test_duplicate_action_id(self):
        registry = ActionRegistry()
        self.assertEqual(registry.register("conv", "act_1"), "accepted")
        self.assertEqual(registry.register("conv", "act_1"), "duplicate")
        self.assertEqual(registry.register("conv2", "act_1"), "accepted")


if __name__ == "__main__":
    unittest.main()
