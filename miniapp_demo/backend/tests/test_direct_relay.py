import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from miniapp_demo.backend.conversations.agent_lane import ActionRecord
from miniapp_demo.backend.conversations.direct_relay import DirectRelay


class SandboxResult:
    def __init__(self, ok=True, miniapp_metadata=None, error=None, exit_code=0):
        self.ok = ok
        self.miniapp_metadata = miniapp_metadata
        self.error = error
        self.exit_code = exit_code


class DirectRelayTests(unittest.IsolatedAsyncioTestCase):
    @patch("miniapp_demo.backend.conversations.direct_relay.get_app")
    @patch("miniapp_demo.backend.conversations.direct_relay.sandbox.run_script", new_callable=AsyncMock)
    async def test_forwards_to_sandbox_and_returns_ui_commands(self, run_script, get_app):
        get_app.return_value = type(
            "Manifest",
            (),
            {
                "script_by_name": lambda self, name: type(
                    "Script",
                    (),
                    {"path": "scripts/hello.py", "visibility": ["ui"]},
                )(),
                "root": __import__("pathlib").Path("/tmp/app"),
            },
        )()
        run_script.return_value = SandboxResult(
            ok=True,
            miniapp_metadata={
                "uiCommands": [
                    {"type": "ui_command", "command": "patch", "payload": {"message": "hi"}}
                ]
            },
        )
        relay = DirectRelay()
        action = ActionRecord(
            action_id="a1",
            conversation_id="conv",
            kind="direct",
            source="ui",
            skill_id="demo",
            name="hello",
            args={"x": 1},
        )
        result = await relay.execute(action)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.ui_commands), 1)
        run_script.assert_awaited_once()

    @patch("miniapp_demo.backend.conversations.direct_relay.get_app")
    async def test_unknown_action(self, get_app):
        get_app.return_value = type(
            "Manifest",
            (),
            {"script_by_name": lambda self, name: None, "root": __import__("pathlib").Path("/tmp")},
        )()
        relay = DirectRelay()
        result = await relay.execute(
            ActionRecord("a1", "conv", "direct", "ui", skill_id="demo", name="missing")
        )
        self.assertFalse(result.ok)
        self.assertIn("unknown action", result.error or "")


if __name__ == "__main__":
    unittest.main()
