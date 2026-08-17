from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from testgen_shared.qwen import _parse_json_output, build_qwen_command, run_qwen


class QwenOutputParsingTests(unittest.TestCase):
    def test_parse_json_output_extracts_session_and_assistant_text(self) -> None:
        payload = [
            {
                "type": "system",
                "subtype": "session_start",
                "session_id": "session-123",
            },
            {
                "type": "assistant",
                "session_id": "session-123",
                "message": {
                    "content": [
                        {"type": "text", "text": "Created tests."},
                        {"type": "text", "text": "Wrote report."},
                    ]
                },
            },
        ]

        session_id, messages, events = _parse_json_output(json.dumps(payload))

        self.assertEqual(session_id, "session-123")
        self.assertEqual(messages, ["Created tests.\nWrote report."])
        self.assertEqual(len(events), 2)

    def test_run_qwen_raises_clear_error_when_executable_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "qwen-output.json"
            with patch("testgen_shared.qwen.subprocess.run", side_effect=FileNotFoundError()):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Could not start Qwen executable 'missing-qwen'",
                ):
                    run_qwen(
                        qwen_bin="missing-qwen",
                        prompt="test",
                        repo_root=Path(temp_dir),
                        model="qwen3-coder-plus",
                        approval_mode="yolo",
                        max_session_turns=1,
                        max_wall_time=None,
                        max_tool_calls=None,
                        output_path=output_path,
                    )

    def test_run_qwen_raises_clear_error_when_stdout_is_not_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "qwen-output.json"

            class Completed:
                returncode = 0
                stdout = "not json"
                stderr = "warning text"

            with patch("testgen_shared.qwen.subprocess.run", return_value=Completed()):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Qwen returned non-JSON stdout despite '--output-format json'",
                ):
                    run_qwen(
                        qwen_bin="qwen",
                        prompt="test",
                        repo_root=Path(temp_dir),
                        model="qwen3-coder-plus",
                        approval_mode="yolo",
                        max_session_turns=1,
                        max_wall_time=None,
                        max_tool_calls=None,
                        output_path=output_path,
                    )

    def test_run_qwen_sends_prompt_via_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "qwen-output.json"

            class Completed:
                returncode = 0
                stdout = "[]"
                stderr = ""

            with patch("testgen_shared.qwen.subprocess.run", return_value=Completed()) as mocked_run:
                run_qwen(
                    qwen_bin="qwen",
                    prompt="prompt through stdin",
                    repo_root=Path(temp_dir),
                    model="qwen3.6-27b-fp8",
                    approval_mode="yolo",
                    max_session_turns=1,
                    max_wall_time=None,
                    max_tool_calls=None,
                    output_path=output_path,
                )

            self.assertEqual(mocked_run.call_args.kwargs["input"], "prompt through stdin")

    def test_build_qwen_command_uses_yolo_switch_for_yolo_mode(self) -> None:
        command = build_qwen_command(
            qwen_bin="qwen",
            model="qwen3.6-27b-fp8",
            approval_mode="yolo",
            max_session_turns=10,
            max_wall_time=None,
            max_tool_calls=None,
        )

        self.assertIn("-y", command)
        self.assertNotIn("--approval-mode", command)
        self.assertNotIn("-p", command)


if __name__ == "__main__":
    unittest.main()
