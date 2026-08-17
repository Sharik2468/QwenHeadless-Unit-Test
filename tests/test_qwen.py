from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from testgen_shared.qwen import _parse_json_output, run_qwen


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
                        max_wall_time="1m",
                        max_tool_calls=1,
                        output_path=output_path,
                    )


if __name__ == "__main__":
    unittest.main()
