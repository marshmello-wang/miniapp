import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from miniapp_demo.backend import app_registry, config, sandbox


class BundledScriptTest(unittest.IsolatedAsyncioTestCase):
    async def _run(
        self,
        app_id: str,
        script_name: str,
        store: Path,
        arguments: dict,
    ) -> sandbox.ScriptResult:
        app_root = config.BUNDLED_APPS_DIR / app_id
        return await sandbox.run_script(
            app_root / "scripts" / script_name,
            app_root,
            store,
            arguments,
        )

    def assert_stdout_is_plain(self, stdout: str) -> None:
        self.assertTrue(stdout.strip())
        self.assertNotIn("structuredContent", stdout)
        self.assertNotIn("agentSignal", stdout)

    async def test_fortune_question_emits_ui_and_ends_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            result = await self._run(
                "fortune-teller",
                "show_question.py",
                Path(directory) / "store",
                {
                    "text": "你更看重什么？",
                    "type": "choice",
                    "options": ["自由", "稳定"],
                },
            )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(
            {
                "uiUpdates": [
                    {
                        "phase": "question",
                        "question": {
                            "text": "你更看重什么？",
                            "type": "choice",
                            "options": ["自由", "稳定"],
                        },
                    }
                ],
                "agentSignal": "end_turn",
            },
            result.miniapp_metadata,
        )
        self.assert_stdout_is_plain(result.stdout)

    async def test_order_query_emits_orders_and_stats(self):
        orders = {
            "orders": [
                {
                    "id": "O-1",
                    "customer": "甲",
                    "amount": 120,
                    "risk": "high",
                    "status": "pending",
                },
                {
                    "id": "O-2",
                    "customer": "乙",
                    "amount": 80,
                    "risk": "low",
                    "status": "approved",
                },
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "store"
            store.mkdir()
            (store / "orders.json").write_text(
                json.dumps(orders, ensure_ascii=False),
                encoding="utf-8",
            )
            result = await self._run(
                "order-review",
                "query.py",
                store,
                {"status": "pending"},
            )

        self.assertTrue(result.ok, result.error)
        self.assertEqual(
            {
                "uiUpdates": [
                    {
                        "orders": [orders["orders"][0]],
                        "stats": {
                            "total": 2,
                            "pending": 1,
                            "approved": 1,
                            "amount_pending": 120,
                        },
                    }
                ],
                "agentSignal": None,
            },
            result.miniapp_metadata,
        )
        self.assert_stdout_is_plain(result.stdout)

    async def test_order_mutation_emits_updated_orders_and_persists_store(self):
        orders = {
            "orders": [
                {
                    "id": "O-1",
                    "customer": "甲",
                    "amount": 120,
                    "risk": "high",
                    "status": "pending",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "store"
            store.mkdir()
            path = store / "orders.json"
            path.write_text(
                json.dumps(orders, ensure_ascii=False),
                encoding="utf-8",
            )
            result = await self._run(
                "order-review",
                "mutate.py",
                store,
                {"orderId": "O-1"},
            )
            persisted = json.loads(path.read_text(encoding="utf-8"))

        expected_order = {**orders["orders"][0], "status": "approved"}
        self.assertTrue(result.ok, result.error)
        self.assertEqual(
            {
                "uiUpdates": [
                    {
                        "orders": [expected_order],
                        "stats": {
                            "total": 1,
                            "pending": 0,
                            "approved": 1,
                            "amount_pending": 0,
                        },
                        "lastAction": {"approved": "O-1", "ok": True},
                    }
                ],
                "agentSignal": None,
            },
            result.miniapp_metadata,
        )
        self.assertEqual([expected_order], persisted["orders"])
        self.assert_stdout_is_plain(result.stdout)


class GeneratedAppScriptTest(unittest.IsolatedAsyncioTestCase):
    async def test_generated_script_uses_runtime_metadata_not_stdout_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            apps_dir = Path(directory) / "apps"
            apps_dir.mkdir()
            with (
                mock.patch.object(config, "APPS_DIR", apps_dir),
                mock.patch.object(config, "ensure_directories"),
            ):
                manifest = app_registry.create_app("Example")

            script = manifest.root / "scripts" / "hello.py"
            result = await sandbox.run_script(
                script,
                manifest.root,
                Path(directory) / "store",
                {},
            )

            self.assertTrue(result.ok, result.error)
            self.assertEqual(
                {
                    "uiUpdates": [{"message": "hello from example"}],
                    "agentSignal": None,
                },
                result.miniapp_metadata,
            )
            self.assertTrue(result.stdout.strip())
            self.assertNotIn("structuredContent", result.stdout)
            self.assertNotIn("agentSignal", result.stdout)
            self.assertIn(
                "from miniapp_runtime import emit_ui",
                script.read_text(encoding="utf-8"),
            )
            self.assertIn(
                "`emit_ui`",
                (manifest.root / "SKILL.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
