import json
import tempfile
import unittest
from pathlib import Path

from miniapp_demo.backend.conversations.event_store import EventStore
from miniapp_demo.backend.conversations.protocol import make_durable_event


class ConversationEventStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EventStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_assigns_monotonic_conversation_seq(self):
        conv = "conv_1"
        seq1 = self.store.append(
            make_durable_event(
                conversation_id=conv,
                event_type="action.accepted",
                actor="runtime",
                payload={"actionId": "a1"},
            )
        )
        seq2 = self.store.append(
            make_durable_event(
                conversation_id=conv,
                event_type="agent_action.enqueued",
                actor="runtime",
                payload={"actionId": "a1"},
            )
        )
        self.assertEqual(seq1, 1)
        self.assertEqual(seq2, 2)

    def test_replay_after_cursor(self):
        conv = "conv_2"
        for index in range(3):
            self.store.append(
                make_durable_event(
                    conversation_id=conv,
                    event_type="direct_action.completed",
                    actor="runtime",
                    payload={"index": index},
                )
            )
        replay = self.store.replay(conv, after=1)
        self.assertEqual([event["conversationSeq"] for event in replay], [2, 3])
        self.assertEqual(replay[0]["payload"]["index"], 1)

    def test_replay_empty_conversation(self):
        self.assertEqual(self.store.replay("conv_missing"), [])

    def test_event_has_required_fields(self):
        conv = "conv_3"
        seq = self.store.append(
            make_durable_event(
                conversation_id=conv,
                event_type="ui.snapshot.requested",
                actor="runtime",
                action_id="act_1",
                skill_id="order-review",
                ui_instance_id="ui_1",
                payload={"snapshotRequestId": "snap_1"},
            )
        )
        events = self.store.replay(conv)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["conversationSeq"], seq)
        self.assertEqual(event["conversationId"], conv)
        self.assertEqual(event["type"], "ui.snapshot.requested")
        self.assertEqual(event["actor"], "runtime")
        self.assertEqual(event["actionId"], "act_1")
        self.assertEqual(event["skillId"], "order-review")
        self.assertEqual(event["uiInstanceId"], "ui_1")
        self.assertIn("eventId", event)
        self.assertIn("ts", event)

    def test_persists_across_store_instances(self):
        conv = "conv_4"
        self.store.append(
            make_durable_event(
                conversation_id=conv,
                event_type="agent.text",
                actor="agent",
                payload={"text": "hello"},
            )
        )
        other = EventStore(Path(self.tmp.name))
        events = other.replay(conv)
        self.assertEqual(len(events), 1)
        self.assertEqual(json.loads(json.dumps(events[0]))["payload"]["text"], "hello")


if __name__ == "__main__":
    unittest.main()
