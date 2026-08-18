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
                },
            )

            self.assertIn("You MUST inspect any existing tests for this control", prompt)
            self.assertIn("existing_tests_preserved", prompt)
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
                },
            )

            self.assertIn("Research found no existing control-specific tests", prompt)
            self.assertIn("must create at least one meaningful headless runtime test file", prompt)

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
