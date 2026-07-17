import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from miniapp_demo.backend.conversations.event_store import EventStore
from miniapp_demo.backend.conversations.runtime import ConversationRuntime
from miniapp_demo.backend.routers import conversations_router


class ConversationsRouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        conversations_router._event_root = root
        conversations_router._event_store = EventStore(root)
        conversations_router._runtime = ConversationRuntime(
            conversations_router._event_store
        )
        app = FastAPI()
        app.include_router(conversations_router.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_submit_agent_action(self):
        response = self.client.post(
            "/api/conversations/conv_test/actions",
            json={
                "actionId": "act_1",
                "kind": "agent",
                "source": "chat",
                "intent": "hello",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "enqueued")

    def test_persisted_events_after_submit(self):
        self.client.post(
            "/api/conversations/conv_sse/actions",
            json={
                "actionId": "act_1",
                "kind": "agent",
                "source": "ui",
                "intent": "approve",
            },
        )
        events = conversations_router._event_store.replay("conv_sse")
        types = [event["type"] for event in events]
        self.assertEqual(types[:2], ["action.accepted", "agent_action.enqueued"])

    def test_duplicate_action_id_conflict(self):
        body = {
            "actionId": "act_dup",
            "kind": "agent",
            "source": "chat",
            "intent": "hello",
        }
        self.assertEqual(self.client.post("/api/conversations/conv_dup/actions", json=body).status_code, 200)
        self.assertEqual(self.client.post("/api/conversations/conv_dup/actions", json=body).status_code, 409)


if __name__ == "__main__":
    unittest.main()
