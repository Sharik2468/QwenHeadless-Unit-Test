from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uikit_testgen.models import ControlManifest, RunConfig
from uikit_testgen.orchestrator import Orchestrator

SAMPLE_CONTROL = "SampleStyledControl"


def build_manifest(styles_root: Path) -> ControlManifest:
    return ControlManifest(
        name=SAMPLE_CONTROL,
        kind="styled_control",
        style_dir=styles_root / SAMPLE_CONTROL,
        relative_dir=SAMPLE_CONTROL,
        group_name=SAMPLE_CONTROL,
    )


class UIKitOrchestratorContextTests(unittest.TestCase):
    def test_research_prompt_for_styled_control_disallows_unit_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifacts = root / ".artifacts"
            styles_root = root / "Controls"
            unit_project = root / "UnitTests/UnitTests.csproj"
            headless_project = root / "HeadlessTests/HeadlessTests.csproj"
            styles_root.mkdir(parents=True)
            unit_project.parent.mkdir(parents=True)
            headless_project.parent.mkdir(parents=True)
            unit_project.write_text("<Project />", encoding="utf-8")
            headless_project.write_text("<Project />", encoding="utf-8")

            config = RunConfig(
                repo_root=root,
                unit_tests_project=unit_project,
                headless_tests_project=headless_project,
                styles_root=styles_root,
                custom_controls_root=None,
                artifacts_dir=artifacts,
            )
            orchestrator = Orchestrator(config)
            manifest = build_manifest(styles_root)

            prompt = orchestrator._build_research_prompt(manifest, artifacts / "research.json")

            self.assertIn("Do NOT plan classic unit tests", prompt)
            self.assertIn("Writing the research summary artifact requested below is required and explicitly allowed.", prompt)
            self.assertIn("Inspect existing control-specific tests, if any", prompt)
            self.assertIn('"status": "none|partial|adequate|stale|unknown"', prompt)
            self.assertIn("next_action", prompt)
            self.assertIn("Do NOT rely on bash-only utilities such as `printf`, `cat`, `head`, or `tail`", prompt)

    def test_generation_prompt_requires_existing_test_review_before_preserving(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifacts = root / ".artifacts"
            styles_root = root / "Controls"
            unit_project = root / "UnitTests/UnitTests.csproj"
            headless_project = root / "HeadlessTests/HeadlessTests.csproj"
            styles_root.mkdir(parents=True)
            unit_project.parent.mkdir(parents=True)
            headless_project.parent.mkdir(parents=True)
            unit_project.write_text("<Project />", encoding="utf-8")
            headless_project.write_text("<Project />", encoding="utf-8")

            config = RunConfig(
                repo_root=root,
                unit_tests_project=unit_project,
                headless_tests_project=headless_project,
                styles_root=styles_root,
                custom_controls_root=None,
                artifacts_dir=artifacts,
            )
            orchestrator = Orchestrator(config)
            manifest = build_manifest(styles_root)

            prompt = orchestrator._build_generation_prompt(
                manifest,
                artifacts / "controls" / SAMPLE_CONTROL / "result.json",
                {
                    "control": {"name": SAMPLE_CONTROL},
                    "existing_test_files": [f"HeadlessTests/{SAMPLE_CONTROL}Tests.cs"],
                    "existing_test_coverage": {"status": "partial"},
                    "next_action": "update_tests",
                },
            )

            self.assertIn("You MUST inspect any existing tests for this control", prompt)
            self.assertIn("generation_outcome", prompt)
            self.assertIn("existing_tests_preserved", prompt)
            self.assertIn("Research next_action", prompt)
            self.assertIn("Do NOT invent alternative field names such as `test_file`, `tests_total`, `tests_passed`, `tests_failed`, or `changes`", prompt)
            self.assertIn("`notes` MUST always be a JSON array of strings", prompt)
            self.assertIn("Do NOT run `dotnet build` or `dotnet test` yourself in this phase", prompt)
            self.assertIn("Do NOT write memory files, scratch summaries, or any other side-car artifacts", prompt)
            self.assertIn("Do NOT rely on bash-only utilities such as `printf`, `cat`, `head`, or `tail`", prompt)
            self.assertIn("compare them against the current control/theme/resource files", prompt)

    def test_generation_prompt_requires_new_tests_when_research_found_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifacts = root / ".artifacts"
            styles_root = root / "Controls"
            unit_project = root / "UnitTests/UnitTests.csproj"
            headless_project = root / "HeadlessTests/UnitTests.csproj"
            styles_root.mkdir(parents=True)
            unit_project.parent.mkdir(parents=True)
            headless_project.parent.mkdir(parents=True)
            unit_project.write_text("<Project />", encoding="utf-8")
            headless_project.write_text("<Project />", encoding="utf-8")

            orchestrator = Orchestrator(
                RunConfig(
                    repo_root=root,
                    unit_tests_project=unit_project,
                    headless_tests_project=headless_project,
                    styles_root=styles_root,
                    custom_controls_root=None,
                    artifacts_dir=artifacts,
                )
            )
            manifest = build_manifest(styles_root)

            prompt = orchestrator._build_generation_prompt(
                manifest,
                artifacts / "controls" / SAMPLE_CONTROL / "result.json",
                {
                    "control": {"name": SAMPLE_CONTROL},
                    "existing_test_files": [],
                    "existing_test_coverage": {"status": "none"},
                    "next_action": "create_tests",
                },
            )

            self.assertIn("Research found no existing control-specific tests", prompt)
            self.assertIn("create_tests -> create meaningful tests", prompt)
            self.assertIn("must create at least one meaningful headless runtime test file", prompt)

    def test_repair_prompt_requires_canonical_result_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifacts = root / ".artifacts"
            styles_root = root / "Controls"
            unit_project = root / "UnitTests/UnitTests.csproj"
            headless_project = root / "HeadlessTests/UnitTests.csproj"
            styles_root.mkdir(parents=True)
            unit_project.parent.mkdir(parents=True)
            headless_project.parent.mkdir(parents=True)
            unit_project.write_text("<Project />", encoding="utf-8")
            headless_project.write_text("<Project />", encoding="utf-8")

            orchestrator = Orchestrator(
                RunConfig(
                    repo_root=root,
                    unit_tests_project=unit_project,
                    headless_tests_project=headless_project,
                    styles_root=styles_root,
                    custom_controls_root=None,
                    artifacts_dir=artifacts,
                )
            )

            prompt = orchestrator._build_repair_prompt(
                SAMPLE_CONTROL,
                {
                    "control": {"name": SAMPLE_CONTROL},
                    "existing_test_files": [],
                    "existing_test_coverage": {"status": "none"},
                    "next_action": "create_tests",
                },
                "build failed",
                "tests failed",
            )

            self.assertIn("use ONLY the canonical fields expected by the orchestrator", prompt)
            self.assertIn("Do NOT emit legacy/free-form fields such as `test_file`, `tests_total`, `tests_passed`, `tests_failed`, or `changes`", prompt)
            self.assertIn("`notes` must remain a JSON array of strings", prompt)
            self.assertIn("Do NOT run `dotnet build` or `dotnet test` yourself in this repair phase", prompt)
            self.assertIn("Do NOT write memory files, scratch summaries, or any side-car artifacts", prompt)
            self.assertIn("Do NOT rely on bash-only utilities such as `printf`, `cat`, `head`, or `tail`", prompt)

    def test_extra_include_directories_collects_external_reference_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            external = root.parent / "external-ref"
            external.mkdir(exist_ok=True)
            artifacts = root / ".artifacts"
            styles_root = root / "Controls"
            unit_project = root / "UnitTests/UnitTests.csproj"
            headless_project = root / "HeadlessTests/HeadlessTests.csproj"
            styles_root.mkdir(parents=True)
            unit_project.parent.mkdir(parents=True)
            headless_project.parent.mkdir(parents=True)
            unit_project.write_text("<Project />", encoding="utf-8")
            headless_project.write_text("<Project />", encoding="utf-8")

            config = RunConfig(
                repo_root=root,
                unit_tests_project=unit_project,
                headless_tests_project=headless_project,
                styles_root=styles_root,
                custom_controls_root=external,
                artifacts_dir=artifacts,
                reference_paths=[external],
            )
            orchestrator = Orchestrator(config)

            include_dirs = orchestrator._extra_include_directories()

            self.assertEqual(include_dirs, [external])


if __name__ == "__main__":
    unittest.main()
