from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from testgen_shared.qwen import QwenRunResult
from uikit_testgen.models import ControlManifest, ControlResult, RunConfig
from uikit_testgen.orchestrator import Orchestrator

SAMPLE_CONTROL = "SampleStyledControl"
SAMPLE_TEST_FILE = f"{SAMPLE_CONTROL}Tests.cs"


class ControlResultParsingTests(unittest.TestCase):
    def test_from_dict_accepts_existing_tests_preserved(self) -> None:
        result = ControlResult.from_dict(
            {
                "control": SAMPLE_CONTROL,
                "status": "verified",
                "generation_outcome": "preserved_existing_tests",
                "existing_tests_preserved": True,
                "notes": ["existing coverage reused"],
            }
        )

        self.assertEqual(result.control, SAMPLE_CONTROL)
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.generation_outcome, "preserved_existing_tests")
        self.assertTrue(result.existing_tests_preserved)
        self.assertEqual(result.notes, ["existing coverage reused"])

    def test_from_dict_ignores_unknown_fields_without_crashing(self) -> None:
        result = ControlResult.from_dict(
            {
                "control": SAMPLE_CONTROL,
                "status": "partial",
                "unexpected": {"value": 1},
                "notes": ["report loaded"],
            }
        )

        self.assertEqual(result.control, SAMPLE_CONTROL)
        self.assertEqual(result.status, "partial")
        self.assertIn("report loaded", result.notes)
        self.assertIn("Ignored unsupported report fields: unexpected", result.notes)

    def test_from_dict_normalizes_legacy_qwen_result_payload(self) -> None:
        result = ControlResult.from_dict(
            {
                "control": SAMPLE_CONTROL,
                "status": "fixed",
                "existing_tests_preserved": False,
                "test_file": f"C:/repo/tests/{SAMPLE_TEST_FILE}",
                "tests_total": 5,
                "tests_passed": 5,
                "tests_failed": 0,
                "changes": ["Fixed one assertion overload."],
                "notes": "Existing tests were corrected.",
            }
        )

        self.assertEqual(result.status, "fixed")
        self.assertEqual(result.generation_outcome, "updated_existing_tests")
        self.assertEqual(result.updated_tests, [f"C:/repo/tests/{SAMPLE_TEST_FILE}"])
        self.assertEqual(result.created_tests, [])
        self.assertIn("Existing tests were corrected.", result.notes)
        self.assertIn("Fixed one assertion overload.", result.notes)

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
                        "control": SAMPLE_CONTROL,
                        "status": "verified",
                        "existing_tests_preserved": True,
                        "unexpected_field": "ignore me",
                    }
                ),
                encoding="utf-8",
            )

            result = orchestrator._load_or_fallback_result(
                report_path=report_path,
                control_name=SAMPLE_CONTROL,
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

            self.assertEqual(result.control, SAMPLE_CONTROL)
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
            style_dir = styles_root / SAMPLE_CONTROL
            related_file = style_dir / f"{SAMPLE_CONTROL}Theme.axaml"
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
                name=SAMPLE_CONTROL,
                kind="styled_control",
                style_dir=style_dir,
                relative_dir=SAMPLE_CONTROL,
                group_name=SAMPLE_CONTROL,
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
            report_path = artifacts_dir / "controls" / SAMPLE_CONTROL / "result.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(
                    {
                        "control": SAMPLE_CONTROL,
                        "status": "partial",
                        "created_tests": [],
                        "updated_tests": [],
                        "existing_tests_preserved": True,
                        "notes": [f"Reviewed existing {SAMPLE_CONTROL} tests against current theme files."],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(
                    orchestrator,
                    "_ensure_research_summary",
                    return_value={
                        "summary": "ok",
                        "existing_test_files": [SAMPLE_TEST_FILE],
                        "next_action": "preserve_tests",
                    },
                ),
                patch.object(orchestrator, "_build_generation_prompt", return_value="prompt"),
                patch.object(orchestrator, "_invoke_generation", return_value=qwen_result),
                patch.object(orchestrator, "_run_builds", return_value=True) as mocked_builds,
                patch.object(orchestrator, "_run_tests", return_value=True) as mocked_tests,
            ):
                orchestrator._process_control(manifest, {"controls": {}})

            self.assertEqual(mocked_builds.call_count, 2)
            self.assertEqual(mocked_tests.call_count, 2)

            result_payload = json.loads(
                (artifacts_dir / "controls" / SAMPLE_CONTROL / "result.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result_payload["status"], "verified")
            self.assertTrue(result_payload["existing_tests_preserved"])
            self.assertEqual(result_payload["generation_outcome"], "preserved_existing_tests")
            self.assertTrue(result_payload["build"]["attempted"])
            self.assertTrue(result_payload["build"]["passed"])
            self.assertTrue(result_payload["build"]["baseline_attempted"])
            self.assertTrue(result_payload["build"]["baseline_passed"])
            self.assertTrue(result_payload["test_run"]["attempted"])
            self.assertTrue(result_payload["test_run"]["passed"])
            self.assertTrue(result_payload["test_run"]["baseline_attempted"])
            self.assertTrue(result_payload["test_run"]["baseline_passed"])
            self.assertIn(
                "Existing tests were reviewed, preserved, and verified against the current control filter.",
                result_payload["notes"],
            )

    def test_process_control_skips_initial_build_when_research_found_no_existing_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo_root = root / "repo"
            repo_root.mkdir()
            unit_project = repo_root / "tests/Unit/Unit.csproj"
            headless_project = repo_root / "tests/Headless/Headless.csproj"
            styles_root = repo_root / "styles"
            style_dir = styles_root / SAMPLE_CONTROL
            related_file = style_dir / f"{SAMPLE_CONTROL}Theme.axaml"
            artifacts_dir = root / "artifacts"
            generated_test_file = headless_project.parent / SAMPLE_TEST_FILE

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
                    max_repair_attempts=1,
                )
            )
            manifest = ControlManifest(
                name=SAMPLE_CONTROL,
                kind="styled_control",
                style_dir=style_dir,
                relative_dir=SAMPLE_CONTROL,
                group_name=SAMPLE_CONTROL,
                related_files=[related_file],
            )
            report_path = artifacts_dir / "controls" / SAMPLE_CONTROL / "result.json"
            initial_result = QwenRunResult(
                returncode=0,
                stdout="[]",
                stderr="",
                session_id="session-initial",
                assistant_messages=["Need to create tests."],
                raw_events=[],
            )
            repair_result = QwenRunResult(
                returncode=0,
                stdout="[]",
                stderr="",
                session_id="session-repair",
                assistant_messages=["Created headless tests."],
                raw_events=[],
            )

            generation_count = {"value": 0}
            invoked_turn_limits: list[int | None] = []

            def fake_invoke_generation(*args, **kwargs):
                generation_count["value"] += 1
                invoked_turn_limits.append(kwargs.get("session_turns"))
                if generation_count["value"] == 1:
                    return initial_result

                generated_test_file.write_text(
                    "await WaitForLayoutAndRender();\n_window.Show();\n",
                    encoding="utf-8",
                )
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps(
                        {
                            "control": SAMPLE_CONTROL,
                            "status": "partial",
                            "created_tests": [SAMPLE_TEST_FILE],
                            "updated_tests": [],
                            "notes": ["Created runtime headless coverage."],
                        }
                    ),
                    encoding="utf-8",
                )
                return repair_result

            with (
                patch.object(
                    orchestrator,
                    "_ensure_research_summary",
                    return_value={"summary": "ok", "existing_test_files": [], "next_action": "create_tests"},
                ),
                patch.object(orchestrator, "_build_generation_prompt", return_value="prompt"),
                patch.object(orchestrator, "_build_repair_prompt", return_value="repair"),
                patch.object(orchestrator, "_invoke_generation", side_effect=fake_invoke_generation),
                patch.object(orchestrator, "_run_builds", return_value=True) as mocked_builds,
                patch.object(orchestrator, "_run_tests", return_value=True) as mocked_tests,
            ):
                orchestrator._process_control(manifest, {"controls": {}})

            self.assertEqual(generation_count["value"], 2)
            self.assertEqual(invoked_turn_limits, [None, orchestrator.config.max_session_turns])
            mocked_builds.assert_called_once()
            mocked_tests.assert_called_once()

            result_payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(result_payload["status"], "verified")
            self.assertEqual(result_payload["created_tests"], [SAMPLE_TEST_FILE])
            self.assertTrue(result_payload["build"]["attempted"])
            self.assertTrue(result_payload["test_run"]["attempted"])

    def test_preserve_existing_tests_does_not_depend_on_python_coverage_gating(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit_project = root / "tests/Unit/Unit.csproj"
            headless_project = root / "tests/Headless/Headless.csproj"
            styles_root = root / "styles"
            unit_project.parent.mkdir(parents=True)
            headless_project.parent.mkdir(parents=True)
            styles_root.mkdir(parents=True)
            unit_project.write_text("<Project />", encoding="utf-8")
            headless_project.write_text("<Project />", encoding="utf-8")

            orchestrator = Orchestrator(
                RunConfig(
                    repo_root=root,
                    unit_tests_project=unit_project,
                    headless_tests_project=headless_project,
                    styles_root=styles_root,
                    custom_controls_root=None,
                    artifacts_dir=root / "artifacts",
                )
            )
            result = ControlResult(
                control=SAMPLE_CONTROL,
                status="partial",
                generation_outcome="preserved_existing_tests",
                existing_tests_preserved=True,
            )

            self.assertTrue(
                orchestrator._should_attempt_verification(
                    result,
                    {
                        "existing_test_files": [SAMPLE_TEST_FILE],
                        "next_action": "preserve_tests",
                        "existing_test_coverage": {"status": "adequate", "files": [SAMPLE_TEST_FILE]},
                    },
                )
            )
            self.assertTrue(
                orchestrator._should_attempt_verification(
                    result,
                    {
                        "existing_test_files": [SAMPLE_TEST_FILE],
                        "next_action": "preserve_tests",
                        "existing_test_coverage": {"status": "partial", "files": [SAMPLE_TEST_FILE]},
                    },
                )
            )

    def test_apply_baseline_context_distinguishes_pre_existing_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit_project = root / "tests/Unit/Unit.csproj"
            headless_project = root / "tests/Headless/Headless.csproj"
            styles_root = root / "styles"
            unit_project.parent.mkdir(parents=True)
            headless_project.parent.mkdir(parents=True)
            styles_root.mkdir(parents=True)
            unit_project.write_text("<Project />", encoding="utf-8")
            headless_project.write_text("<Project />", encoding="utf-8")

            orchestrator = Orchestrator(
                RunConfig(
                    repo_root=root,
                    unit_tests_project=unit_project,
                    headless_tests_project=headless_project,
                    styles_root=styles_root,
                    custom_controls_root=None,
                    artifacts_dir=root / "artifacts",
                )
            )
            build_log = root / "build.log"
            test_log = root / "test.log"
            build_log.write_text("error in SharedTests.cs", encoding="utf-8")
            test_log.write_text("baseline test failure", encoding="utf-8")

            result = ControlResult(
                control=SAMPLE_CONTROL,
                status="partial",
                created_tests=[SAMPLE_TEST_FILE],
            )
            result.build = {"attempted": True, "passed": False, "log_file": str(build_log)}
            result.test_run = {"attempted": True, "passed": False, "log_file": str(test_log), "failed_tests": []}

            orchestrator._apply_baseline_context(
                result,
                baseline={
                    "attempted": True,
                    "build": {"attempted": True, "passed": False, "log_file": str(root / "baseline-build.log")},
                    "test_run": {"attempted": True, "passed": False, "log_file": str(root / "baseline-test.log")},
                },
                build_log_path=build_log,
                test_log_path=test_log,
            )

            self.assertEqual(result.build["failure_origin"], "pre_existing_build_failure")
            self.assertEqual(result.test_run["failure_origin"], "pre_existing_test_failure")

    def test_extract_qwen_error_summary_reads_error_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unit_project = root / "tests/Unit/Unit.csproj"
            headless_project = root / "tests/Headless/Headless.csproj"
            styles_root = root / "styles"
            unit_project.parent.mkdir(parents=True)
            headless_project.parent.mkdir(parents=True)
            styles_root.mkdir(parents=True)
            unit_project.write_text("<Project />", encoding="utf-8")
            headless_project.write_text("<Project />", encoding="utf-8")

            orchestrator = Orchestrator(
                RunConfig(
                    repo_root=root,
                    unit_tests_project=unit_project,
                    headless_tests_project=headless_project,
                    styles_root=styles_root,
                    custom_controls_root=None,
                    artifacts_dir=root / "artifacts",
                )
            )

            summary = orchestrator._extract_qwen_error_summary(
                '{"error":{"type":"FatalTurnLimitedError","message":"Reached max session turns","code":53}}'
            )

            self.assertEqual(
                summary,
                "FatalTurnLimitedError (code=53): Reached max session turns",
            )


if __name__ == "__main__":
    unittest.main()
