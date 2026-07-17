import unittest

from miniapp_demo.backend.conversations.agent_events import agent_event_to_durable
from miniapp_demo.backend.protocol import APP_EMIT_TOOL
from common.agent_framework.user_interface.content_blocks import ToolCallBlock
from common.agent_framework.user_interface.events import Event


def _tool_result_event(block: ToolCallBlock) -> Event:
    return Event.create(
        event_id="evt-1",
        session_id="conv-1",
        task_id="task-1",
        event_type="tool_result",
        content=[block],
    )


class AgentEventsAppEmitTest(unittest.TestCase):
    def test_app_emit_open_command_becomes_ui_command_open(self):
        block = ToolCallBlock(
            tool_name=APP_EMIT_TOOL,
            tool_input={
                "structuredContent": {
                    "command": "open",
                    "skillId": "fortune-teller",
                    "route": "/reading",
                }
            },
            call_id="call-1",
        )
        out = agent_event_to_durable(_tool_result_event(block), action_id="act-1")

        self.assertEqual(1, len(out))
        self.assertEqual("ui.command", out[0]["type"])
        payload = out[0]["payload"]
        self.assertEqual("open", payload["command"])
        self.assertEqual("fortune-teller", payload["skillId"])
        self.assertEqual("/reading", payload["route"])

    def test_app_emit_patch_default_when_no_command(self):
        block = ToolCallBlock(
            tool_name=APP_EMIT_TOOL,
            tool_input={"structuredContent": {"phase": "narration", "text": "hi"}},
            call_id="call-2",
        )
        out = agent_event_to_durable(_tool_result_event(block), action_id="act-1")

        self.assertEqual(1, len(out))
        self.assertEqual("ui.command", out[0]["type"])
        payload = out[0]["payload"]
        self.assertEqual("patch", payload["command"])
        self.assertEqual({"phase": "narration", "text": "hi"}, payload["payload"])


if __name__ == "__main__":
    unittest.main()
