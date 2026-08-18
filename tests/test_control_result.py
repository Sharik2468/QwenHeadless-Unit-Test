from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from testgen_shared.qwen import QwenRunResult
from uikit_testgen.models import ControlManifest, ControlResult, RunConfig
from uikit_testgen.orchestrator import Orchestrator


class ControlResultParsingTests(unittest.TestCase):
    def test_from_dict_accepts_existing_tests_preserved(self) -> None:
        result = ControlResult.from_dict(
            {
                "control": "AdornerLayer",
                "status": "verified",
                "existing_tests_preserved": True,
                "notes": ["existing coverage reused"],
            }
        )

        self.assertEqual(result.control, "AdornerLayer")
        self.assertEqual(result.status, "verified")
        self.assertTrue(result.existing_tests_preserved)
        self.assertEqual(result.notes, ["existing coverage reused"])

    def test_from_dict_ignores_unknown_fields_without_crashing(self) -> None:
        result = ControlResult.from_dict(
            {
                "control": "AdornerLayer",
                "status": "partial",
                "unexpected": {"value": 1},
                "notes": ["report loaded"],
            }
        )

        self.assertEqual(result.control, "AdornerLayer")
        self.assertEqual(result.status, "partial")
        self.assertIn("report loaded", result.notes)
        self.assertIn("Ignored unsupported report fields: unexpected", result.notes)

    def test_orchestrator_loads_extended_report_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            repo_root.mkdir()
            unit_project = repo_root / "tests/Unit/Unit.csproj"
            headless_project = repo_root / "tests/Headless/Headless.csproj"
            styles_root = repo_root / "styles"
            artifacts_dir = root / "artifacts"

            unit_project.parent.mkdir(parents=True)
            headless_project.parent.mkdir(parents=True)
            styles_root.mkdir(parents=True)
            unit_project.write_text("<Project />", encoding="utf-8")
            headless_project.write_text("<Project />", encoding="utf-8")

            orchestrator = Orchestrator(
                RunConfig(
                    repo_root=repo_root,
                    unit_tests_project=unit_project,
                    headless_tests_project=headless_project,
                    styles_root=styles_root,
                    custom_controls_root=None,
                    artifacts_dir=artifacts_dir,
                )
            )

            report_path = artifacts_dir / "result.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(
                    {
                        "control": "AdornerLayer",
                        "status": "verified",
                        "existing_tests_preserved": True,
                        "unexpected_field": "ignore me",
                    }
                ),
                encoding="utf-8",
            )

            result = orchestrator._load_or_fallback_result(
                report_path=report_path,
                control_name="AdornerLayer",
                build_log_path=artifacts_dir / "build.log",
                test_log_path=artifacts_dir / "test.log",
                qwen_result=QwenRunResult(
                    returncode=0,
                    stdout="[]",
                    stderr="",
                    session_id=None,
                    assistant_messages=[],
                    raw_events=[],
                ),
                build_ok=True,
                test_ok=True,
            )

            self.assertEqual(result.control, "AdornerLayer")
            self.assertEqual(result.status, "verified")
            self.assertTrue(result.existing_tests_preserved)
            self.assertIn("Ignored unsupported report fields: unexpected_field", result.notes)

    def test_process_control_verifies_existing_tests_when_generation_makes_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            repo_root.mkdir()
            unit_project = repo_root / "tests/Unit/Unit.csproj"
            headless_project = repo_root / "tests/Headless/Headless.csproj"
            styles_root = repo_root / "styles"
            style_dir = styles_root / "AdornerLayer"
            related_file = style_dir / "AdornerLayerTheme.axaml"
            artifacts_dir = root / "artifacts"

            unit_project.parent.mkdir(parents=True)
            headless_project.parent.mkdir(parents=True)
            style_dir.mkdir(parents=True)
            unit_project.write_text("<Project />", encoding="utf-8")
            headless_project.write_text("<Project />", encoding="utf-8")
            related_file.write_text("<Styles />", encoding="utf-8")

            orchestrator = Orchestrator(
                RunConfig(
                    repo_root=repo_root,
                    unit_tests_project=unit_project,
                    headless_tests_project=headless_project,
                    styles_root=styles_root,
                    custom_controls_root=None,
                    artifacts_dir=artifacts_dir,
                )
            )
            manifest = ControlManifest(
                name="AdornerLayer",
                kind="styled_control",
                style_dir=style_dir,
                relative_dir="AdornerLayer",
                group_name="AdornerLayer",
                related_files=[related_file],
            )
            qwen_result = QwenRunResult(
                returncode=0,
                stdout="[]",
                stderr="",
                session_id="session-1",
                assistant_messages=["Existing coverage already looks sufficient."],
                raw_events=[],
            )

            with (
                patch.object(orchestrator, "_ensure_research_summary", return_value={"summary": "ok"}),
                patch.object(orchestrator, "_build_generation_prompt", return_value="prompt"),
                patch.object(orchestrator, "_invoke_generation", return_value=qwen_result),
                patch.object(orchestrator, "_run_builds", return_value=True) as mocked_builds,
                patch.object(orchestrator, "_run_tests", return_value=True) as mocked_tests,
            ):
                orchestrator._process_control(manifest, {"controls": {}})

            mocked_builds.assert_called_once()
            mocked_tests.assert_called_once()

            result_payload = json.loads(
                (artifacts_dir / "controls" / "AdornerLayer" / "result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result_payload["status"], "verified")
            self.assertTrue(result_payload["existing_tests_preserved"])
            self.assertTrue(result_payload["build"]["attempted"])
            self.assertTrue(result_payload["build"]["passed"])
            self.assertTrue(result_payload["test_run"]["attempted"])
            self.assertTrue(result_payload["test_run"]["passed"])
            self.assertIn(
                "No test files were changed; existing tests matching the control filter were executed and passed.",
                result_payload["notes"],
            )


if __name__ == "__main__":
    unittest.main()
