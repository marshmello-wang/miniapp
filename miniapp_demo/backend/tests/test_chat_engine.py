import unittest
from unittest.mock import patch

from common.agent_framework.user_interface.content_blocks import TextBlock

from miniapp_demo.backend.chat_engine import ChatEngine


class _Event:
    def __init__(self, event_type, content=()):
        self.event_type = event_type
        self.content = list(content)

    def to_dict(self):
        return {"event_type": self.event_type}


class _ChatEngine(ChatEngine):
    async def _stream_chat(
        self,
        session_id,
        task_id,
        user_message,
        history,
    ):
        yield _Event("reasoning", [TextBlock("AI 回复")])
        yield _Event("task_complete")


class ChatEngineTest(unittest.IsolatedAsyncioTestCase):
    async def test_completes_round_before_emitting_done(self):
        engine = _ChatEngine()

        with (
            patch(
                "miniapp_demo.backend.chat_engine.stores.load_history",
                return_value=[],
            ),
            patch(
                "miniapp_demo.backend.chat_engine.stores.start_round",
                return_value=3,
            ),
            patch(
                "miniapp_demo.backend.chat_engine.stores.complete_round",
            ) as complete_round,
        ):
            stream = engine.chat_action("session-1", "你好", "request-1")
            text = await anext(stream)
            self.assertEqual("text", text["data"]["type"])

            done = await anext(stream)

        self.assertEqual("done", done["data"]["type"])
        complete_round.assert_called_once()
        self.assertEqual("AI 回复", complete_round.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
