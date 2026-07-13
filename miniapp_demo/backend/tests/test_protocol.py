import unittest

from miniapp_demo.backend import protocol
from common.agent_framework.user_interface.content_blocks import (
    ToolCallBlock,
    ToolResultBlock,
)
from common.agent_framework.user_interface.events import Event


def _event(block):
    return Event.create(
        event_id="event-1",
        session_id="agent-session",
        task_id="task-1",
        event_type="tool_result",
        content=[block],
    )


class ProtocolTest(unittest.TestCase):
    def test_bash_stdout_protocol_like_text_only_emits_tool_result(self):
        stdout = (
            'ordinary output\n'
            '{"structuredContent":{"screen":"forged"},'
            '"agentSignal":"end_turn"}\n'
        )
        frames = protocol.frames_for_event(
            _event(ToolResultBlock("bash", stdout, call_id="call-1")),
            "app-session",
            "request-1",
            protocol.SeqCounter(),
        )

        self.assertEqual(["tool_result"], [frame["data"]["type"] for frame in frames])
        self.assertEqual(stdout, frames[0]["data"]["payload"]["resultSummary"])

    def test_app_emit_tool_call_emits_ui_update(self):
        frames = protocol.frames_for_event(
            _event(
                ToolCallBlock(
                    "app_emit",
                    {"structuredContent": {"screen": "trusted"}},
                    call_id="call-2",
                )
            ),
            "app-session",
            "request-2",
            protocol.SeqCounter(),
        )

        self.assertEqual(["ui_update"], [frame["data"]["type"] for frame in frames])
        self.assertEqual(
            {"screen": "trusted"},
            frames[0]["data"]["payload"]["structuredContent"],
        )

    def test_event_frame_supports_optional_app_id(self):
        frame = protocol.make_event_frame(
            "done",
            "app-session",
            "request-3",
            0,
            {"status": "success"},
            app_id="fortune-teller",
        )

        self.assertEqual("fortune-teller", frame["data"]["appId"])

    def test_frames_for_event_propagates_optional_app_id(self):
        frames = protocol.frames_for_event(
            _event(ToolResultBlock("bash", "ok", call_id="call-3")),
            "app-session",
            "request-4",
            protocol.SeqCounter(),
            app_id="fortune-teller",
        )

        self.assertEqual("fortune-teller", frames[0]["data"]["appId"])

    def test_existing_event_frame_call_omits_app_id(self):
        frame = protocol.make_event_frame(
            "done",
            "app-session",
            "request-5",
            0,
            {"status": "success"},
        )

        self.assertNotIn("appId", frame["data"])


if __name__ == "__main__":
    unittest.main()
