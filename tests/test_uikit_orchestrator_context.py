from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uikit_testgen.models import ControlManifest, RunConfig
from uikit_testgen.orchestrator import Orchestrator


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
            manifest = ControlManifest(
                name="AdornerLayer",
                kind="styled_control",
                style_dir=styles_root / "AdornerLayer",
                relative_dir="AdornerLayer",
                group_name="AdornerLayer",
            )

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
            manifest = ControlManifest(
                name="AdornerLayer",
                kind="styled_control",
                style_dir=styles_root / "AdornerLayer",
                relative_dir="AdornerLayer",
                group_name="AdornerLayer",
            )

            prompt = orchestrator._build_generation_prompt(
                manifest,
                artifacts / "controls" / "AdornerLayer" / "result.json",
                {
                    "control": {"name": "AdornerLayer"},
                    "existing_test_files": ["HeadlessTests/AdornerLayerTests.cs"],
                    "existing_test_coverage": {"status": "partial"},
                },
            )

            self.assertIn("You MUST inspect any existing tests for this control", prompt)
            self.assertIn("existing_tests_preserved", prompt)
            self.assertIn("compare them against the current control/theme/resource files", prompt)

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
