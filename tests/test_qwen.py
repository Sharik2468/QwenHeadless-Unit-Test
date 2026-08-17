from __future__ import annotations

import json
import unittest

from uikit_testgen.qwen import _parse_json_output


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


if __name__ == "__main__":
    unittest.main()
