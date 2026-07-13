import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from miniapp_demo.backend import script_metadata
from miniapp_demo.script_sdk import miniapp_runtime


class ScriptMetadataTest(unittest.TestCase):
    def test_multiple_ui_updates_and_end_turn_are_aggregated(self):
        with script_metadata.result_file() as path:
            with mock.patch.dict(
                os.environ, {"MINIAPP_RESULT_PATH": str(path)}, clear=False
            ):
                miniapp_runtime.emit_ui({"phase": "question"})
                miniapp_runtime.emit_ui({"phase": "answer"})
                miniapp_runtime.end_turn()

            self.assertEqual(
                {
                    "uiUpdates": [
                        {"phase": "question"},
                        {"phase": "answer"},
                    ],
                    "agentSignal": "end_turn",
                },
                script_metadata.parse_result_file(path),
            )

    def test_metadata_is_read_after_process_exit_and_stdout_is_ignored(self):
        with script_metadata.result_file() as path:
            env = dict(os.environ)
            env["MINIAPP_RESULT_PATH"] = str(path)
            process = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from miniapp_demo.script_sdk.miniapp_runtime "
                        "import emit_ui, end_turn; "
                        "print('{\"type\":\"done\"}'); "
                        "emit_ui({'source': 'metadata'}); end_turn()"
                    ),
                ],
                cwd=Path(__file__).parents[3],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual('{"type":"done"}\n', process.stdout)
            self.assertEqual(
                {
                    "uiUpdates": [{"source": "metadata"}],
                    "agentSignal": "end_turn",
                },
                script_metadata.parse_result_file(path),
            )

    def test_result_files_are_unique_and_mode_0600(self):
        first = script_metadata.create_result_file()
        second = script_metadata.create_result_file()
        try:
            self.assertNotEqual(first, second)
            self.assertEqual(0o600, stat.S_IMODE(first.stat().st_mode))
            self.assertEqual(0o600, stat.S_IMODE(second.stat().st_mode))
        finally:
            script_metadata.cleanup_result_file(first)
            script_metadata.cleanup_result_file(second)

    def test_fchmod_failure_closes_and_removes_result_file(self):
        failed_fd = None

        def fail_fchmod(fd, _mode):
            nonlocal failed_fd
            failed_fd = fd
            raise OSError("injected fchmod failure")

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(
                script_metadata.os, "fchmod", side_effect=fail_fchmod
            ):
                with self.assertRaisesRegex(OSError, "injected fchmod failure"):
                    script_metadata.create_result_file(Path(directory))

            self.assertEqual([], list(Path(directory).iterdir()))
            self.assertIsNotNone(failed_fd)
            with self.assertRaises(OSError):
                os.fstat(failed_fd)

    def test_result_file_is_cleaned_after_success_and_failure(self):
        with script_metadata.result_file() as success_path:
            self.assertTrue(success_path.exists())
        self.assertFalse(success_path.exists())

        failure_path = None
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with script_metadata.result_file() as path:
                failure_path = path
                raise RuntimeError("boom")
        self.assertIsNotNone(failure_path)
        self.assertFalse(failure_path.exists())

    def test_runtime_requires_result_path(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            calls = [
                lambda: miniapp_runtime.emit_ui({"phase": "question"}),
                miniapp_runtime.end_turn,
            ]
            for call in calls:
                with self.subTest(call=call):
                    with self.assertRaises(Exception) as caught:
                        call()
                    self.assertIsInstance(
                        caught.exception,
                        miniapp_runtime.MiniAppRuntimeError,
                    )
                    self.assertRegex(
                        str(caught.exception),
                        "MINIAPP_RESULT_PATH.*required",
                    )

    def test_runtime_rejects_non_object_structured_content(self):
        with self.assertRaises(TypeError):
            miniapp_runtime.emit_ui(["not", "an", "object"])

    def test_runtime_rejects_non_finite_numbers_as_non_json(self):
        with script_metadata.result_file() as path:
            with mock.patch.dict(
                os.environ, {"MINIAPP_RESULT_PATH": str(path)}, clear=False
            ):
                for value in (float("nan"), float("inf"), float("-inf")):
                    with self.subTest(value=value):
                        with self.assertRaisesRegex(
                            RuntimeError, "strict JSON"
                        ):
                            miniapp_runtime.emit_ui({"value": value})
            self.assertEqual("", path.read_text(encoding="utf-8"))

    def test_runtime_rejects_non_string_object_keys_recursively(self):
        invalid_values = [
            {1: "top-level"},
            {"nested": [{"deeper": {2: "nested"}}]},
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                with script_metadata.result_file() as path:
                    with mock.patch.dict(
                        os.environ,
                        {"MINIAPP_RESULT_PATH": str(path)},
                        clear=False,
                    ):
                        with self.assertRaisesRegex(
                            miniapp_runtime.MiniAppRuntimeError,
                            "object keys must be strings",
                        ):
                            miniapp_runtime.emit_ui(value)
                    self.assertEqual("", path.read_text(encoding="utf-8"))

    def test_runtime_wraps_utf8_encoding_failures(self):
        with script_metadata.result_file() as path:
            with mock.patch.dict(
                os.environ, {"MINIAPP_RESULT_PATH": str(path)}, clear=False
            ):
                with self.assertRaises(Exception) as caught:
                    miniapp_runtime.emit_ui({"value": "\ud800"})
                self.assertIsInstance(
                    caught.exception, miniapp_runtime.MiniAppRuntimeError
                )
                self.assertRegex(str(caught.exception), "UTF-8")
            self.assertEqual("", path.read_text(encoding="utf-8"))

    def test_runtime_wraps_file_write_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(
                os.environ,
                {"MINIAPP_RESULT_PATH": directory},
                clear=False,
            ):
                with self.assertRaises(Exception) as caught:
                    miniapp_runtime.emit_ui({"phase": "question"})
                self.assertIsInstance(
                    caught.exception, miniapp_runtime.MiniAppRuntimeError
                )
                self.assertRegex(str(caught.exception), "write metadata")

    def test_read_ndjson_returns_validated_events(self):
        with script_metadata.result_file() as path:
            path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "ui_update",
                                "structuredContent": {"screen": "one"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "agent_signal",
                                "agentSignal": "end_turn",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(
                [
                    {
                        "type": "ui_update",
                        "structuredContent": {"screen": "one"},
                    },
                    {
                        "type": "agent_signal",
                        "agentSignal": "end_turn",
                    },
                ],
                script_metadata.read_ndjson(path),
            )

    def test_rejects_invalid_json_unknown_done_and_non_object_content(self):
        invalid_lines = [
            "{not json}",
            json.dumps({"type": "unknown"}),
            json.dumps({"type": "done"}),
            json.dumps(
                {"type": "ui_update", "structuredContent": ["not", "object"]}
            ),
            json.dumps(
                {"type": "agent_signal", "agentSignal": "keep_going"}
            ),
        ]

        for line in invalid_lines:
            with self.subTest(line=line):
                with script_metadata.result_file() as path:
                    path.write_text(line + "\n", encoding="utf-8")
                    with self.assertRaises(script_metadata.MetadataValidationError):
                        script_metadata.parse_result_file(path)

    def test_reader_rejects_non_finite_json_constants(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                with script_metadata.result_file() as path:
                    path.write_text(
                        (
                            '{"type":"ui_update",'
                            f'"structuredContent":{{"value":{constant}}}}}\n'
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        script_metadata.MetadataValidationError,
                        "invalid JSON.*line 1",
                    ):
                        script_metadata.parse_result_file(path)

    def test_reader_rejects_exponent_overflow_as_non_finite(self):
        for number in ("1e400", "-1e400"):
            with self.subTest(number=number):
                with script_metadata.result_file() as path:
                    path.write_text(
                        (
                            '{"type":"ui_update",'
                            f'"structuredContent":{{"nested":[{number}]}}}}\n'
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        script_metadata.MetadataValidationError,
                        "non-finite",
                    ):
                        script_metadata.parse_result_file(path)

    def test_backend_rejects_nested_non_string_object_keys(self):
        with self.assertRaisesRegex(
            script_metadata.MetadataValidationError,
            "object keys must be strings",
        ):
            script_metadata.validate_event(
                {
                    "type": "ui_update",
                    "structuredContent": {
                        "nested": [{"deeper": {1: "invalid"}}]
                    },
                }
            )

    def test_reader_rejects_escaped_surrogates_in_nested_strings_and_keys(self):
        invalid_lines = [
            (
                b'{"type":"ui_update","structuredContent":'
                b'{"value":"\\ud800"}}\n'
            ),
            (
                b'{"type":"ui_update","structuredContent":'
                b'{"nested":["\\udfff"]}}\n'
            ),
            (
                b'{"type":"ui_update","structuredContent":'
                b'{"\\ud800":"value"}}\n'
            ),
        ]
        for raw_line in invalid_lines:
            with self.subTest(raw_line=raw_line):
                with script_metadata.result_file() as path:
                    path.write_bytes(raw_line)
                    with self.assertRaisesRegex(
                        script_metadata.MetadataValidationError,
                        "UTF-8",
                    ):
                        script_metadata.parse_result_file(path)

    def test_rejects_line_and_total_file_size_limits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            line_path = Path(temp_dir) / "line.ndjson"
            line_path.write_bytes(b"x" * 17 + b"\n")
            with self.assertRaises(script_metadata.MetadataSizeError):
                script_metadata.read_ndjson(
                    line_path, max_line_bytes=16, max_file_bytes=128
                )

            total_path = Path(temp_dir) / "total.ndjson"
            total_path.write_bytes(b"{}\n{}\n")
            with self.assertRaises(script_metadata.MetadataSizeError):
                script_metadata.read_ndjson(
                    total_path, max_line_bytes=16, max_file_bytes=5
                )


if __name__ == "__main__":
    unittest.main()
