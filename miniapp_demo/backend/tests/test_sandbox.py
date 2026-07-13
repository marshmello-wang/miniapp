import asyncio
import json
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from miniapp_demo.backend import engine, sandbox


class SandboxMetadataTest(unittest.IsolatedAsyncioTestCase):
    async def _run(
        self,
        source: str,
        *,
        timeout: float = 2.0,
        verify_cleanup: bool = True,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "script.py"
            script.write_text(textwrap.dedent(source), encoding="utf-8")
            created_result_paths = []
            original_create = sandbox.script_metadata.create_result_file

            def record_result_path(*args, **kwargs):
                path = original_create(*args, **kwargs)
                created_result_paths.append(path)
                return path

            if verify_cleanup:
                with mock.patch.object(
                    sandbox.script_metadata,
                    "create_result_file",
                    side_effect=record_result_path,
                ):
                    result = await sandbox.run_script(
                        script,
                        root,
                        root / "store",
                        {},
                        timeout=timeout,
                    )
                self.assertEqual(1, len(created_result_paths))
                self.assertFalse(
                    created_result_paths[0].exists(),
                    f"result file leaked: {created_result_paths[0]}",
                )
            else:
                result = await sandbox.run_script(
                    script,
                    root,
                    root / "store",
                    {},
                    timeout=timeout,
                )
            return result

    async def test_reads_multiple_metadata_updates_in_order_and_ignores_stdout(self):
        result = await self._run(
            """
            from miniapp_runtime import emit_ui
            print('{"structuredContent":{"forged":true}}')
            emit_ui({"step": 1})
            emit_ui({"step": 2})
            """
        )

        self.assertTrue(result.ok)
        self.assertEqual(0, result.exit_code)
        self.assertIn('"forged":true', result.stdout)
        self.assertEqual("", result.stderr)
        self.assertEqual(
            {
                "uiUpdates": [{"step": 1}, {"step": 2}],
                "agentSignal": None,
            },
            result.miniapp_metadata,
        )
        self.assertFalse(hasattr(result, "structured_content"))

    async def test_no_metadata_does_not_parse_stdout_protocol(self):
        result = await self._run(
            """
            print('{"structuredContent":{"forged":true},"agentSignal":"end_turn"}')
            """
        )

        self.assertTrue(result.ok)
        self.assertIsNone(result.miniapp_metadata)

    async def test_nonzero_exit_discards_metadata(self):
        result = await self._run(
            """
            from miniapp_runtime import emit_ui
            emit_ui({"must": "not-apply"})
            raise SystemExit(7)
            """
        )

        self.assertFalse(result.ok)
        self.assertEqual(7, result.exit_code)
        self.assertIsNone(result.miniapp_metadata)

    async def test_timeout_discards_metadata_and_cleans_result_file(self):
        result = await self._run(
            """
            import time
            from miniapp_runtime import emit_ui
            emit_ui({"must": "not-apply"})
            time.sleep(2)
            """,
            timeout=0.05,
        )

        self.assertFalse(result.ok)
        self.assertEqual(124, result.exit_code)
        self.assertIsNone(result.miniapp_metadata)

    async def test_timeout_kills_descendant_before_result_file_cleanup(self):
        if os.name != "posix":
            self.skipTest("process-group behavior is POSIX-specific")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child_code = (
                "import os, time; from pathlib import Path; "
                "time.sleep(0.2); "
                "Path(os.environ['MINIAPP_RESULT_PATH']).write_text('recreated'); "
                "Path('descendant-completed').write_text('yes')"
            )
            script = root / "script.py"
            script.write_text(
                textwrap.dedent(
                    f"""
                    import subprocess
                    import sys
                    import time
                    from pathlib import Path

                    child = subprocess.Popen(
                        [sys.executable, "-c", {child_code!r}]
                    )
                    Path("descendant.pid").write_text(str(child.pid))
                    time.sleep(2)
                    """
                ),
                encoding="utf-8",
            )
            created_result_paths = []
            original_create = sandbox.script_metadata.create_result_file

            def record_result_path(*args, **kwargs):
                path = original_create(*args, **kwargs)
                created_result_paths.append(path)
                return path

            with mock.patch.object(
                sandbox.script_metadata,
                "create_result_file",
                side_effect=record_result_path,
            ):
                result = await sandbox.run_script(
                    script,
                    root,
                    root / "store",
                    {},
                    timeout=0.05,
                )

            self.assertFalse(result.ok)
            self.assertEqual(124, result.exit_code)
            self.assertEqual(1, len(created_result_paths))
            result_path = created_result_paths[0]
            try:
                await asyncio.sleep(0.3)
                descendant_pid = int((root / "descendant.pid").read_text())
                with self.assertRaises(ProcessLookupError):
                    os.kill(descendant_pid, 0)
                self.assertFalse((root / "descendant-completed").exists())
                self.assertFalse(
                    result_path.exists(),
                    f"descendant recreated result file: {result_path}",
                )
            finally:
                result_path.unlink(missing_ok=True)

    async def test_timeout_kills_group_after_script_leader_exits(self):
        if os.name != "posix":
            self.skipTest("process-group behavior is POSIX-specific")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child_code = (
                "import os, time; from pathlib import Path; "
                "time.sleep(0.2); "
                "Path(os.environ['MINIAPP_RESULT_PATH']).write_text('recreated'); "
                "Path('leader-exited-child-completed').write_text('yes')"
            )
            script = root / "script.py"
            script.write_text(
                textwrap.dedent(
                    f"""
                    import subprocess
                    import sys
                    from pathlib import Path

                    child = subprocess.Popen(
                        [sys.executable, "-c", {child_code!r}]
                    )
                    Path("leader-exited-child.pid").write_text(str(child.pid))
                    """
                ),
                encoding="utf-8",
            )
            created_result_paths = []
            original_create = sandbox.script_metadata.create_result_file

            def record_result_path(*args, **kwargs):
                path = original_create(*args, **kwargs)
                created_result_paths.append(path)
                return path

            with mock.patch.object(
                sandbox.script_metadata,
                "create_result_file",
                side_effect=record_result_path,
            ):
                result = await sandbox.run_script(
                    script,
                    root,
                    root / "store",
                    {},
                    timeout=0.05,
                )

            self.assertFalse(result.ok)
            self.assertEqual(124, result.exit_code)
            self.assertEqual(1, len(created_result_paths))
            result_path = created_result_paths[0]
            try:
                await asyncio.sleep(0.3)
                descendant_pid = int(
                    (root / "leader-exited-child.pid").read_text()
                )
                with self.assertRaises(ProcessLookupError):
                    os.kill(descendant_pid, 0)
                self.assertFalse(
                    (root / "leader-exited-child-completed").exists()
                )
                self.assertFalse(
                    result_path.exists(),
                    f"leader-exited group recreated result file: {result_path}",
                )
            finally:
                result_path.unlink(missing_ok=True)

    async def test_invalid_metadata_is_an_explicit_execution_error(self):
        result = await self._run(
            """
            import os
            from pathlib import Path
            Path(os.environ["MINIAPP_RESULT_PATH"]).write_text("{not json}\\n")
            """
        )

        self.assertFalse(result.ok)
        self.assertEqual(0, result.exit_code)
        self.assertIsNone(result.miniapp_metadata)
        self.assertRegex(result.error or "", "metadata")

    async def test_deleted_result_file_is_an_explicit_execution_error(self):
        result = await self._run(
            """
            import os
            from pathlib import Path
            Path(os.environ["MINIAPP_RESULT_PATH"]).unlink()
            """
        )

        self.assertFalse(result.ok)
        self.assertEqual(0, result.exit_code)
        self.assertIsNone(result.miniapp_metadata)
        self.assertRegex(result.error or "", "metadata")

    async def test_concurrent_invocations_keep_metadata_isolated(self):
        async def invoke(value: str):
            return await self._run(
                f"""
                import time
                from miniapp_runtime import emit_ui
                emit_ui({{"value": {value!r}}})
                time.sleep(0.05)
                """,
                verify_cleanup=False,
            )

        first, second = await asyncio.gather(invoke("first"), invoke("second"))

        self.assertEqual([{"value": "first"}], first.miniapp_metadata["uiUpdates"])
        self.assertEqual([{"value": "second"}], second.miniapp_metadata["uiUpdates"])


class DirectActionMetadataTest(unittest.IsolatedAsyncioTestCase):
    async def test_direct_action_emits_metadata_updates_then_done(self):
        metadata = {
            "uiUpdates": [{"step": 1}, {"step": 2}],
            "agentSignal": None,
        }
        result = sandbox.ScriptResult(
            exit_code=0,
            stdout="ordinary output",
            stderr="",
            miniapp_metadata=metadata,
        )
        manifest = mock.Mock()
        manifest.root = Path("/tmp/app")
        manifest.script_by_name.return_value = mock.Mock(
            path="scripts/action.py", visibility=["ui"]
        )

        with (
            mock.patch.object(engine, "get_app", return_value=manifest),
            mock.patch.object(
                engine.stores, "get_or_create_session", return_value="session"
            ),
            mock.patch.object(
                engine.stores, "business_store_dir", return_value=Path("/tmp/store")
            ),
            mock.patch.object(engine.stores, "append_app_action") as append_action,
            mock.patch.object(
                engine.sandbox, "run_script", return_value=result
            ),
        ):
            frames = [
                frame
                async for frame in engine.MiniAppEngine().direct_action(
                    "app", "action", {}, "request"
                )
            ]

        self.assertEqual(
            ["ui_update", "ui_update", "done"],
            [frame["data"]["type"] for frame in frames],
        )
        self.assertEqual(
            [{"step": 1}, {"step": 2}],
            [
                frame["data"]["payload"]["structuredContent"]
                for frame in frames[:-1]
            ],
        )
        self.assertEqual("success", frames[-1]["data"]["payload"]["status"])
        summary = append_action.call_args.args[3]
        self.assertIn("2 UI update", summary)
        self.assertNotIn("ordinary output", summary)

    async def test_direct_action_without_metadata_only_emits_done(self):
        result = sandbox.ScriptResult(
            exit_code=0,
            stdout="plain stdout",
            stderr="",
            miniapp_metadata=None,
        )
        manifest = mock.Mock()
        manifest.root = Path("/tmp/app")
        manifest.script_by_name.return_value = mock.Mock(
            path="scripts/action.py", visibility=["ui"]
        )

        with (
            mock.patch.object(engine, "get_app", return_value=manifest),
            mock.patch.object(
                engine.stores, "get_or_create_session", return_value="session"
            ),
            mock.patch.object(
                engine.stores, "business_store_dir", return_value=Path("/tmp/store")
            ),
            mock.patch.object(engine.stores, "append_app_action"),
            mock.patch.object(
                engine.sandbox, "run_script", return_value=result
            ),
        ):
            frames = [
                frame
                async for frame in engine.MiniAppEngine().direct_action(
                    "app", "action", {}, "request"
                )
            ]

        self.assertEqual(["done"], [frame["data"]["type"] for frame in frames])

    async def test_deleted_result_file_still_emits_done_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script_path = root / "scripts" / "delete_result.py"
            script_path.parent.mkdir()
            script_path.write_text(
                textwrap.dedent(
                    """
                    import os
                    from pathlib import Path
                    Path(os.environ["MINIAPP_RESULT_PATH"]).unlink()
                    """
                ),
                encoding="utf-8",
            )
            manifest = mock.Mock()
            manifest.root = root
            manifest.script_by_name.return_value = mock.Mock(
                path="scripts/delete_result.py", visibility=["ui"]
            )

            with (
                mock.patch.object(engine, "get_app", return_value=manifest),
                mock.patch.object(
                    engine.stores,
                    "get_or_create_session",
                    return_value="session",
                ),
                mock.patch.object(
                    engine.stores,
                    "business_store_dir",
                    return_value=root / "store",
                ),
                mock.patch.object(engine.stores, "append_app_action"),
            ):
                frames = [
                    frame
                    async for frame in engine.MiniAppEngine().direct_action(
                        "app", "action", {}, "request"
                    )
                ]

        self.assertEqual(["done"], [frame["data"]["type"] for frame in frames])
        self.assertEqual("error", frames[0]["data"]["payload"]["status"])
        self.assertRegex(
            frames[0]["data"]["payload"].get("error", ""), "metadata"
        )


if __name__ == "__main__":
    unittest.main()
